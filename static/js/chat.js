// Live chat with an outgoing queue (v1.1.1, CHG-003).
//
// * Every message gets a one-time id (client_id). The server saves each id only once,
//   so a message that is sent again after a dropped connection never appears twice.
// * Messages written while offline or while the connection is down wait in a queue
//   (kept in this browser, so they survive a page reload) and are sent automatically,
//   in order, as soon as the connection is back. They show as "Waiting to send".
// * The chat reconnects by itself and fetches any messages it missed meanwhile.
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
  var historyUrl = "/conversations/" + conversationId + "/";
  var statusLine = document.getElementById("chat-status");
  var outboxKey = "findit-outbox-" + userId + "-" + conversationId;
  var MAX_QUEUE = 20;
  var socket = null;
  var retryDelay = 1000;
  var everConnected = false;
  var stopped = false;

  function setStatus(text) { if (statusLine) statusLine.textContent = text || ""; }

  function newId() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return String(Date.now()) + "-" + Math.random().toString(16).slice(2);
  }

  // ---- queue (kept in localStorage; falls back to memory) ----
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
    var bubble = panel.querySelector('[data-client-id="' + clientId + '"]');
    if (bubble) bubble.remove();
  }

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

  function dropEmpty() { var empty = panel.querySelector(".chat-empty"); if (empty) empty.remove(); }

  function addMessage(message) {
    if (message.client_id) {
      var pending = panel.querySelector('[data-client-id="' + message.client_id + '"]');
      if (pending) pending.remove();
    }
    if (panel.querySelector('[data-message-id="' + message.id + '"]')) return;
    dropEmpty();
    var article = bubble(message.sender, formatTime(message.sent_at), message.text, String(message.sender_id) === userId);
    article.setAttribute("data-message-id", message.id);
    panel.appendChild(article);
    panel.scrollTop = panel.scrollHeight;
  }

  function showPending(item) {
    if (panel.querySelector('[data-client-id="' + item.id + '"]')) return;
    dropEmpty();
    var article = bubble("You", "Waiting to send…", item.text, true);
    article.classList.add("is-pending");
    article.setAttribute("data-client-id", item.id);
    panel.appendChild(article);
    panel.scrollTop = panel.scrollHeight;
  }

  function flushQueue() {
    if (!socket || socket.readyState !== WebSocket.OPEN || !canSend) return;
    loadQueue().forEach(function (item) {
      socket.send(JSON.stringify({ message: item.text, client_id: item.id }));
    });
  }

  // After a reconnect: add messages that arrived while we were offline.
  function catchUp() {
    if (!window.fetch) return;
    fetch(historyUrl, { credentials: "same-origin" }).then(function (r) { return r.ok ? r.text() : ""; }).then(function (html) {
      if (!html) return;
      var doc = new DOMParser().parseFromString(html, "text/html");
      doc.querySelectorAll("#chat-messages [data-message-id]").forEach(function (fresh) {
        var id = fresh.getAttribute("data-message-id");
        if (!panel.querySelector('[data-message-id="' + id + '"]')) {
          dropEmpty();
          panel.appendChild(document.importNode(fresh, true));
        }
      });
      // Keep queued bubbles at the end.
      panel.querySelectorAll(".is-pending").forEach(function (node) { panel.appendChild(node); });
      panel.scrollTop = panel.scrollHeight;
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
        if (data.client_id) {
          var waiting = loadQueue().some(function (item) { return item.id === data.client_id; });
          if (waiting) removeFromQueue(data.client_id);
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
          // Not sent: give the text back so it is not lost.
          if (item && input && !input.value) input.value = item.text;
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
    retryDelay = Math.min(retryDelay * 2, 30000);
  }

  window.addEventListener("online", function () {
    if (!socket || socket.readyState === WebSocket.CLOSED) { retryDelay = 1000; connect(); }
  });

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
  connect();

  if (!form || !input) return;
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text || !canSend) return;
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
