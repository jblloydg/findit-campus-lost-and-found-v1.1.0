// Find-IT live chat (v1.1.1).
//
// Sending (CHG-003)
// * Every message gets a one-time id (client_id); the server saves each id only once, so a
//   message sent again after a dropped connection never appears twice.
// * Messages written while the connection is down wait in a queue kept in this browser
//   (it survives a reload). They show as "Waiting to send…" and are sent automatically,
//   in order, when the chat reconnects by itself. No resend button is needed.
//
// Reading (PERF-001, CHG-005) — Messenger style
// * The page starts with the newest ~8 KB of messages. Scrolling up loads older messages
//   by themselves after a short pause; pages are sized by bytes, not by a fixed count.
// * At most MAX_ON_SCREEN messages stay on screen; the far end is dropped and loads again
//   when you scroll back. New live messages are drawn in one batch per screen frame.
// * Search finds messages in this chat (after you pause typing) and jumps to them.
document.addEventListener("DOMContentLoaded", function () {
  var panel = document.getElementById("chat-messages");
  var form = document.getElementById("chat-form");
  var input = document.getElementById("chat-input");
  if (!panel) return;

  var conversationId = panel.getAttribute("data-conversation");
  var canSend = panel.getAttribute("data-can-send") === "true";
  var userId = document.body.getAttribute("data-user-id") || "anon";
  var protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  var socketUrl = protocol + "//" + window.location.host + "/ws/conversations/" + conversationId + "/";
  var messagesUrl = "/conversations/" + conversationId + "/messages/";
  var statusLine = document.getElementById("chat-status");
  var historyStatus = panel.querySelector("[data-history-status]");
  var jumpButton = document.querySelector("[data-chat-jump]");
  var outboxKey = "findit-outbox-" + userId + "-" + conversationId;
  var MAX_QUEUE = 20;
  var MAX_ON_SCREEN = 400;
  var EDGE_PX = 160;          // how close to the top/bottom before loading more
  var LOAD_PAUSE_MS = 250;    // slight delay so fast scrolling does not flood the server
  var socket = null;
  var retryDelay = 1000;
  var everConnected = false;
  var stopped = false;

  // ---- what is on screen ----
  var known = {};
  var hasOlder = panel.getAttribute("data-has-older") === "true";
  var atLatest = true;        // false after opening an old search result or scrolling far back
  var loadingOlder = false, loadingNewer = false;

  function setStatus(text) { if (statusLine) statusLine.textContent = text || ""; }
  function messageNodes() { return panel.querySelectorAll("[data-message-id]"); }
  function idOf(node) { return parseInt(node.getAttribute("data-message-id"), 10); }
  function oldestId() { var n = messageNodes(); return n.length ? idOf(n[0]) : 0; }
  function newestId() { var n = messageNodes(); return n.length ? idOf(n[n.length - 1]) : 0; }
  function setHistoryStatus() {
    if (!historyStatus) return;
    historyStatus.textContent = loadingOlder ? "Loading older messages…"
      : hasOlder ? "Scroll up for older messages"
      : (messageNodes().length ? "Start of the conversation" : "");
  }
  messageNodes().forEach(function (node) { known[idOf(node)] = true; });

  function newId() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return String(Date.now()) + "-" + Math.random().toString(16).slice(2);
  }

  // ---- outgoing queue (kept in localStorage; falls back to memory) ----
  var memoryQueue = [];
  function loadQueue() {
    try { return JSON.parse(window.localStorage.getItem(outboxKey) || "[]"); } catch (e) { return memoryQueue.slice(); }
  }
  function saveQueue(queue) {
    memoryQueue = queue.slice();
    try { window.localStorage.setItem(outboxKey, JSON.stringify(queue)); } catch (e) {}
  }
  function removeFromQueue(clientId) {
    saveQueue(loadQueue().filter(function (item) { return item.id !== clientId; }));
    var node = panel.querySelector('[data-client-id="' + clientId + '"]');
    if (node) node.remove();
  }

  // ---- drawing ----
  function formatTime(value) {
    var date = new Date(value);
    return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }
  function bubble(sender, timeText, text, mine) {
    var article = document.createElement("article");
    article.className = "chat-message" + (mine ? " mine" : "");
    var box = document.createElement("div");
    box.className = "message-bubble";
    var meta = document.createElement("div");
    meta.className = "message-meta";
    var name = document.createElement("strong");
    name.textContent = sender;
    var time = document.createElement("time");
    time.textContent = timeText;
    var body = document.createElement("p");
    body.textContent = text;
    meta.append(name, time);
    box.append(meta, body);
    article.appendChild(box);
    return article;
  }
  function messageNode(message) {
    var article = bubble(message.sender, formatTime(message.sent_at), message.text, String(message.sender_id) === userId);
    article.setAttribute("data-message-id", message.id);
    return article;
  }
  function dropEmpty() { var empty = panel.querySelector(".chat-empty"); if (empty) empty.remove(); }
  function bottomAnchor() {
    return panel.querySelector(".is-pending") || (jumpButton && jumpButton.parentNode === panel ? jumpButton : null);
  }
  function fragmentOf(messages) {
    var fragment = document.createDocumentFragment();
    messages.forEach(function (m) {
      if (known[m.id]) return;
      known[m.id] = true;
      fragment.appendChild(messageNode(m));
    });
    return fragment;
  }
  function trimTop() {
    var nodes = messageNodes();
    for (var i = 0; i < nodes.length - MAX_ON_SCREEN; i++) { delete known[idOf(nodes[i])]; nodes[i].remove(); hasOlder = true; }
  }
  function trimBottom() {
    var nodes = messageNodes();
    for (var i = nodes.length - 1; i >= MAX_ON_SCREEN; i--) { delete known[idOf(nodes[i])]; nodes[i].remove(); atLatest = false; }
  }
  function nearBottom() { return panel.scrollHeight - panel.scrollTop - panel.clientHeight < 120; }
  function showJump(text) {
    if (!jumpButton) return;
    jumpButton.hidden = atLatest && !text;
    jumpButton.textContent = text || "↓ Jump to latest";
  }

  // Live messages: batched, one draw per screen frame.
  var incoming = [];
  var drawScheduled = false;
  function addMessage(message) {
    if (message.client_id) {
      var pending = panel.querySelector('[data-client-id="' + message.client_id + '"]');
      if (pending) pending.remove();
    }
    if (known[message.id]) return;
    if (!atLatest) {
      showJump("↓ New messages");   // reading old messages: do not pull the reader away
      return;
    }
    incoming.push(message);
    if (!drawScheduled) { drawScheduled = true; window.requestAnimationFrame(drawIncoming); }
  }
  function drawIncoming() {
    drawScheduled = false;
    if (!incoming.length) return;
    var stick = nearBottom();
    dropEmpty();
    panel.insertBefore(fragmentOf(incoming.sort(function (a, b) { return a.id - b.id; })), bottomAnchor());
    incoming = [];
    if (stick) { trimTop(); panel.scrollTop = panel.scrollHeight; }
    setHistoryStatus();
  }

  // ---- history: older / newer / latest / around a search result ----
  function getJson(url, signal) {
    return fetch(url, { credentials: "same-origin", signal: signal }).then(function (r) {
      return r.json().then(function (data) { data._status = r.status; return data; });
    });
  }
  function loadOlder() {
    if (loadingOlder || !hasOlder || !window.fetch) return;
    var before = oldestId();
    if (!before) return;
    loadingOlder = true; setHistoryStatus();
    getJson(messagesUrl + "?before=" + before).then(function (data) {
      if (data._status === 429) { window.setTimeout(function () { loadingOlder = false; loadOlder(); }, 3000); return; }
      var fromBottom = panel.scrollHeight - panel.scrollTop;
      var first = messageNodes()[0];
      panel.insertBefore(fragmentOf(data.messages || []), first || bottomAnchor());
      hasOlder = !!data.has_older;
      panel.scrollTop = panel.scrollHeight - fromBottom;   // keep the reader's place
      trimBottom(); showJump();
      loadingOlder = false; setHistoryStatus();
    }).catch(function () { loadingOlder = false; setHistoryStatus(); });
  }
  function loadNewer() {
    if (loadingNewer || atLatest || !window.fetch) return;
    loadingNewer = true;
    getJson(messagesUrl + "?after=" + newestId()).then(function (data) {
      if (data._status === 429) { window.setTimeout(function () { loadingNewer = false; loadNewer(); }, 3000); return; }
      var anchor = messageNodes()[messageNodes().length - 1];
      var anchorTop = anchor ? anchor.getBoundingClientRect().top : 0;
      panel.insertBefore(fragmentOf(data.messages || []), bottomAnchor());
      atLatest = !data.has_newer;
      trimTop();
      if (anchor) panel.scrollTop += anchor.getBoundingClientRect().top - anchorTop;  // keep the reader's place
      showJump(); setHistoryStatus();
      loadingNewer = false;
    }).catch(function () { loadingNewer = false; });
  }
  function replaceWith(data, focusId) {
    messageNodes().forEach(function (node) { node.remove(); });
    known = {};
    incoming = [];
    dropEmpty();
    panel.insertBefore(fragmentOf(data.messages || []), bottomAnchor());
    hasOlder = !!data.has_older;
    atLatest = !data.has_newer;
    setHistoryStatus(); showJump();
    var target = focusId && panel.querySelector('[data-message-id="' + focusId + '"]');
    if (target) {
      target.classList.add("is-found");
      panel.scrollTop = target.offsetTop - panel.offsetTop - panel.clientHeight / 2;
      window.setTimeout(function () { target.classList.remove("is-found"); }, 4000);
    } else {
      panel.scrollTop = panel.scrollHeight;
    }
  }
  function jumpToLatest() {
    return getJson(messagesUrl + "?latest=1").then(function (data) {
      if (data._status === 200) replaceWith(data, null);
    }).catch(function () {});
  }
  if (jumpButton) jumpButton.addEventListener("click", jumpToLatest);

  // Scrolling near the top (or the bottom, when reading back) loads more after a short pause.
  var scrollTimer = null;
  panel.addEventListener("scroll", function () {
    if (scrollTimer) return;
    scrollTimer = window.setTimeout(function () {
      scrollTimer = null;
      if (panel.scrollTop < EDGE_PX) loadOlder();
      else if (!atLatest && panel.scrollHeight - panel.scrollTop - panel.clientHeight < EDGE_PX) loadNewer();
    }, LOAD_PAUSE_MS);
  }, { passive: true });

  // ---- search inside this chat ----
  var searchInput = document.getElementById("chat-search-input");
  var searchBox = document.getElementById("chat-search-results");
  var searchTimer = null, searchAbort = null;
  function searchNote(text, keep) {
    if (!keep) searchBox.innerHTML = "";
    var note = document.createElement("div");
    note.className = "chat-search-note";
    note.textContent = text;
    searchBox.appendChild(note);
    searchBox.hidden = false;
  }
  function highlighted(snippet, query) {
    var span = document.createElement("span");
    var lower = snippet.toLowerCase(), q = query.toLowerCase(), at = 0, hit;
    while (q && (hit = lower.indexOf(q, at)) !== -1) {
      span.appendChild(document.createTextNode(snippet.slice(at, hit)));
      var mark = document.createElement("mark");
      mark.textContent = snippet.slice(hit, hit + q.length);
      span.appendChild(mark);
      at = hit + q.length;
    }
    span.appendChild(document.createTextNode(snippet.slice(at)));
    return span;
  }
  function runSearch() {
    var query = searchInput.value.trim();
    if (searchAbort) searchAbort.abort();
    if (query.length < 2) { searchBox.hidden = true; return; }
    searchAbort = window.AbortController ? new AbortController() : null;
    searchNote("Searching…");
    getJson(messagesUrl + "?q=" + encodeURIComponent(query), searchAbort && searchAbort.signal).then(function (data) {
      if (searchInput.value.trim() !== query) return;   // an older answer: ignore
      if (data._status === 429) { searchNote(data.error || "Too many searches. Wait a moment."); return; }
      if (!data.results || !data.results.length) { searchNote("No messages found."); return; }
      searchBox.innerHTML = "";
      data.results.forEach(function (r) {
        var button = document.createElement("button");
        button.type = "button";
        button.setAttribute("data-result-id", r.id);
        var small = document.createElement("small");
        small.textContent = r.sender + " · " + formatTime(r.sent_at);
        button.append(highlighted(r.snippet, query), small);
        searchBox.appendChild(button);
      });
      if (data.results.length >= 30) searchNote("Showing the newest 30 matches. Type more words to narrow it down.", true);
      searchBox.hidden = false;
    }).catch(function (error) { if (!error || error.name !== "AbortError") searchNote("Search is not available right now."); });
  }
  if (searchInput && searchBox) {
    searchInput.addEventListener("input", function () {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(runSearch, 450);   // wait until typing pauses
    });
    searchInput.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { searchInput.value = ""; searchBox.hidden = true; }
      if (event.key === "Enter") { event.preventDefault(); window.clearTimeout(searchTimer); runSearch(); }
    });
    searchBox.addEventListener("click", function (event) {
      var button = event.target.closest && event.target.closest("[data-result-id]");
      if (!button) return;
      var id = button.getAttribute("data-result-id");
      searchBox.hidden = true;
      getJson(messagesUrl + "?around=" + id).then(function (data) {
        if (data._status === 200) replaceWith(data, id);
        else setStatus(data.error || "That message could not be opened.");
      }).catch(function () {});
    });
    document.addEventListener("click", function (event) {
      if (!event.target.closest || !event.target.closest("[data-chat-search]")) searchBox.hidden = true;
    });
  }

  // ---- sending ----
  function showPending(item) {
    if (panel.querySelector('[data-client-id="' + item.id + '"]')) return;
    dropEmpty();
    var article = bubble("You", "Waiting to send…", item.text, true);
    article.classList.add("is-pending");
    article.setAttribute("data-client-id", item.id);
    panel.insertBefore(article, jumpButton && jumpButton.parentNode === panel ? jumpButton : null);
    panel.scrollTop = panel.scrollHeight;
  }
  function flushQueue() {
    if (!socket || socket.readyState !== WebSocket.OPEN || !canSend) return;
    loadQueue().forEach(function (item) { socket.send(JSON.stringify({ message: item.text, client_id: item.id })); });
  }
  // After a reconnect: fetch only what arrived while we were offline (when reading the latest).
  function catchUp() {
    if (!window.fetch || !atLatest) return;
    getJson(messagesUrl + "?after=" + newestId()).then(function (data) {
      if (data._status !== 200) return;
      (data.messages || []).forEach(addMessage);
      if (data.has_newer) window.setTimeout(catchUp, 500);
    }).catch(function () {});
  }

  function connect() {
    if (stopped) return;
    try { socket = new WebSocket(socketUrl); } catch (e) { scheduleReconnect(); return; }
    socket.addEventListener("open", function () {
      retryDelay = 1000;
      setStatus(loadQueue().length ? "Connected. Sending your waiting messages…" : "");
      if (everConnected) catchUp();
      everConnected = true;
    });
    socket.addEventListener("message", function (event) {
      var data;
      try { data = JSON.parse(event.data); } catch (error) { return; }
      if (data.type === "connection") {
        canSend = !!data.can_send;
        if (canSend) flushQueue();
        else if (loadQueue().length) {
          loadQueue().forEach(function (item) { removeFromQueue(item.id); });
          setStatus("This conversation is read-only now, so waiting messages were not sent.");
        }
        return;
      }
      if (data.type === "message") {
        if (data.client_id && loadQueue().some(function (item) { return item.id === data.client_id; })) {
          removeFromQueue(data.client_id);
          if (!loadQueue().length) setStatus("");
        }
        addMessage(data);
      }
      if (data.type === "event" && data.event === "question") refreshQuestions();
      if (data.type === "error") {
        setStatus(data.message);
        if (data.client_id) {
          var item = loadQueue().filter(function (q) { return q.id === data.client_id; })[0];
          removeFromQueue(data.client_id);
          if (item && input && !input.value) input.value = item.text;   // not sent: give the text back
        }
      }
    });
    socket.addEventListener("close", function (event) {
      if (event.code === 4403) { stopped = true; setStatus("You no longer have access to this chat. Reload the page."); return; }
      scheduleReconnect();
    });
  }
  function scheduleReconnect() {
    if (stopped) return;
    var waiting = loadQueue().length;
    setStatus((navigator.onLine === false ? "You are offline." : "Connection lost.") +
      (waiting ? " " + waiting + " message" + (waiting === 1 ? " is" : "s are") + " waiting and will be sent automatically." : " Reconnecting…"));
    window.setTimeout(connect, retryDelay);
    retryDelay = Math.min(retryDelay * 2, 10000);
  }
  var reconnectNow = function () {
    if (!stopped && (!socket || socket.readyState === WebSocket.CLOSED)) { retryDelay = 1000; connect(); }
  };
  window.addEventListener("online", reconnectNow);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) reconnectNow(); });

  // Refresh question cards and the claim strip when the other side sends or answers a question.
  var refreshing = false;
  function refreshQuestions() {
    var typing = document.activeElement && document.activeElement.closest && document.activeElement.closest(".question-card");
    if (refreshing || typing) return;
    refreshing = true;
    fetch(window.location.pathname, { credentials: "same-origin" }).then(function (r) { return r.text(); }).then(function (html) {
      var doc = new DOMParser().parseFromString(html, "text/html");
      ["question-cards"].forEach(function (id) {
        var fresh = doc.getElementById(id), current = document.getElementById(id);
        if (fresh && current) current.innerHTML = fresh.innerHTML;
      });
      var freshStrip = doc.querySelector(".claim-strip"), strip = document.querySelector(".claim-strip");
      if (freshStrip && strip) strip.innerHTML = freshStrip.innerHTML;
    }).catch(function () {}).then(function () { refreshing = false; });
  }

  // Messages left in the queue from an earlier visit show again and are sent on connect.
  loadQueue().forEach(showPending);
  panel.scrollTop = panel.scrollHeight;
  setHistoryStatus();
  connect();

  if (!form || !input) return;
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text || !canSend) return;
    if (!atLatest) jumpToLatest();
    var queue = loadQueue();
    // Same text pressed twice before it is confirmed = one message.
    if (queue.some(function (item) { return item.text === text; })) { input.value = ""; return; }
    if (queue.length >= MAX_QUEUE) { setStatus("Too many messages are waiting. Wait for the connection to come back."); return; }
    var item = { id: newId(), text: text };
    queue.push(item);
    saveQueue(queue);
    showPending(item);
    input.value = "";
    input.focus();
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ message: item.text, client_id: item.id }));
    } else {
      setStatus("Not connected. Your message is waiting and will be sent automatically.");
    }
  });
});
