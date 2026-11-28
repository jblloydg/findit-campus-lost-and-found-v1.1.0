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
//
// Photos and videos (CHG-006)
// * Picked files wait in an upload queue saved on this device (IndexedDB, survives a reload)
//   and are uploaded one at a time with a progress bar, then show "Processing…" while the
//   server re-encodes them. A lost connection just pauses the queue; it continues by itself.
// * In the chat, photos show their small preview first and videos load only when played,
//   so media never holds up the text.
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
  // BUG-022: the same format as the page itself ("Nov 28 · 3:30 p.m."), so a message looks the same
  // when it arrives live and after a reload.
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function formatTime(value) {
    var date = new Date(value);
    if (isNaN(date.getTime())) return "";
    var hour = date.getHours() % 12 || 12;
    return MONTHS[date.getMonth()] + " " + date.getDate() + " · " + hour + ":" +
      String(date.getMinutes()).padStart(2, "0") + " " + (date.getHours() < 12 ? "a.m." : "p.m.");
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
  function attachmentNode(a) {
    if (!a) return null;
    if (a.kind === "PHOTO") {
      var link = document.createElement("a");
      link.className = "chat-media"; link.href = a.url; link.target = "_blank"; link.rel = "noopener";
      var img = document.createElement("img");
      img.src = a.preview_url || a.url; img.alt = "Photo sent in the chat";
      img.loading = "lazy"; img.decoding = "async";
      if (a.width) { img.width = a.width; img.height = a.height; }
      link.appendChild(img);
      return link;
    }
    var video = document.createElement("video");
    video.className = "chat-media"; video.controls = true; video.preload = "none";
    video.setAttribute("playsinline", "");
    if (a.preview_url) video.poster = a.preview_url;
    if (a.width) { video.width = a.width; video.height = a.height; }
    video.src = a.url;
    // v2.0.0: length and size badge under each video, e.g. "▶ 0:42 · 3.1 MB".
    var wrap = document.createElement("span");
    wrap.className = "chat-media-wrap";
    var badge = document.createElement("span");
    badge.className = "media-badge";
    badge.textContent = "▶ " + durationLabel(a.duration) + " · " + sizeLabel(a.bytes);
    wrap.append(video, badge);
    return wrap;
  }
  function durationLabel(seconds) {
    var s = Math.round(Number(seconds) || 0);
    return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
  }
  function sizeLabel(bytes) {
    var b = Number(bytes) || 0;
    if (b < 1024) return b + " bytes";
    if (b < 1024 * 1024) return (b / 1024).toFixed(1) + " KB";
    return (b / 1024 / 1024).toFixed(1) + " MB";
  }
  function messageNode(message) {
    var article = bubble(message.sender, formatTime(message.sent_at), message.text, String(message.sender_id) === userId);
    article.setAttribute("data-message-id", message.id);
    if (!message.text) { var p = article.querySelector("p"); if (p) p.remove(); }
    var media = attachmentNode(message.attachment);
    if (media) article.querySelector(".message-bubble").appendChild(media);
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

  // ---- photos and videos: upload queue saved on this device ----
  var uploadForm = form && form.getAttribute("data-upload-url") ? form : null;
  var fileInput = document.getElementById("chat-file");
  var uploads = {};            // client id -> {item, node, state}
  var uploading = false;
  var DB_NAME = "findit-chat-uploads", STORE = "uploads";
  function openDb() {
    return new Promise(function (resolve, reject) {
      if (!window.indexedDB) { reject(new Error("no indexedDB")); return; }
      var request = window.indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = function () { request.result.createObjectStore(STORE, { keyPath: "id" }); };
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error); };
    });
  }
  function dbDo(mode, work) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, mode);
        var result = work(tx.objectStore(STORE));
        tx.oncomplete = function () { resolve(result && result.result !== undefined ? result.result : result); db.close(); };
        tx.onerror = function () { reject(tx.error); db.close(); };
      });
    }).catch(function () { return null; });   // private mode etc.: queue only in memory
  }
  function dbSave(item) { return dbDo("readwrite", function (s) { return s.put(item); }); }
  function dbDelete(id) { return dbDo("readwrite", function (s) { return s.delete(id); }); }
  function dbMine() {
    return dbDo("readonly", function (s) { return s.getAll(); }).then(function (all) {
      return (all || []).filter(function (item) { return item.conversation === conversationId && item.user === userId; });
    });
  }
  function csrfToken() {
    var field = form && form.querySelector("input[name=csrfmiddlewaretoken]");
    return field ? field.value : "";
  }
  function mediaBubble(item) {
    var node = bubble("You", item.isVideo ? "Video · waiting to send…" : "Photo · waiting to send…", item.name, true);
    node.classList.add("is-pending");
    node.setAttribute("data-client-id", "att-" + item.id);
    var box = node.querySelector(".message-bubble");
    if (!item.isVideo && window.URL && item.blob) {
      var img = document.createElement("img");
      img.className = "chat-local-preview"; img.alt = ""; img.src = URL.createObjectURL(item.blob);
      box.appendChild(img);
    }
    var bar = document.createElement("span");
    bar.className = "chat-upload-progress";
    bar.appendChild(document.createElement("span"));
    box.appendChild(bar);
    panel.insertBefore(node, jumpButton && jumpButton.parentNode === panel ? jumpButton : null);
    panel.scrollTop = panel.scrollHeight;
    return node;
  }
  function uploadNote(entry, text, failed) {
    var time = entry.node.querySelector("time");
    if (time) time.textContent = text;
    if (failed) {
      entry.node.classList.add("is-failed");
      var bar = entry.node.querySelector(".chat-upload-progress");
      if (bar) bar.remove();
      if (!entry.node.querySelector(".chat-upload-dismiss")) {
        var dismiss = document.createElement("button");
        dismiss.type = "button"; dismiss.className = "link-button chat-upload-dismiss"; dismiss.textContent = "Remove";
        dismiss.addEventListener("click", function () { entry.node.remove(); });
        entry.node.querySelector(".message-bubble").appendChild(dismiss);
      }
    }
  }
  function finishUpload(id, failedText) {
    var entry = uploads[id];
    dbDelete(id);
    if (!entry) return;
    delete uploads[id];
    if (failedText) uploadNote(entry, failedText, true);
  }
  function queueFiles(files) {
    if (!uploadForm) return;
    var photoMb = parseFloat(uploadForm.getAttribute("data-photo-mb") || "5");
    var videoMb = parseFloat(uploadForm.getAttribute("data-video-mb") || "20");
    var leftAttr = uploadForm.getAttribute("data-media-left");
    var left = leftAttr === null ? Infinity : parseInt(leftAttr, 10) - Object.keys(uploads).length;
    Array.prototype.forEach.call(files, function (file) {
      var isVideo = /^video\//.test(file.type) || /\.(mp4|mov|webm|3gp|mkv|m4v)$/i.test(file.name);
      var isPhoto = /^image\/(jpeg|png|webp|avif)$/.test(file.type) || /\.(jpe?g|png|webp|avif)$/i.test(file.name);   // BUG-025: + AVIF
      if (!isVideo && !isPhoto) { setStatus(file.name + (/\.hei[cf]$/i.test(file.name) ? ": HEIC photos can't be sent; pick it from the photo library (it sends a JPG) or save it as JPG." : ": only photos (JPG, PNG, WebP, AVIF) and videos can be sent.")); return; }
      var limitMb = isVideo ? videoMb : photoMb;
      if (file.size > limitMb * 1024 * 1024) { setStatus(file.name + ": " + (isVideo ? "videos" : "photos") + " can be up to " + limitMb + " MB."); return; }
      if (left <= 0) { setStatus("Unverified accounts can send 3 photos or videos per chat. Verify your email to send more."); return; }
      left -= 1;
      var item = { id: newId(), conversation: conversationId, user: userId, name: file.name, type: file.type, isVideo: isVideo, blob: file };
      uploads[item.id] = { item: item, node: mediaBubble(item), state: "queued" };
      dbSave(item);
    });
    pumpUploads();
  }
  function pumpUploads() {
    if (uploading || !uploadForm) return;
    var nextId = Object.keys(uploads).filter(function (id) { return uploads[id].state === "queued"; })[0];
    if (!nextId) return;
    var entry = uploads[nextId];
    uploading = true;
    entry.state = "uploading";
    var data = new FormData();
    data.append("file", entry.item.blob, entry.item.name);
    data.append("client_id", entry.item.id);
    var xhr = new XMLHttpRequest();
    xhr.open("POST", uploadForm.getAttribute("data-upload-url"));
    xhr.setRequestHeader("X-CSRFToken", csrfToken());
    xhr.upload.onprogress = function (event) {
      if (!event.lengthComputable) return;
      var fill = entry.node.querySelector(".chat-upload-progress span");
      if (fill) fill.style.width = Math.round(event.loaded / event.total * 100) + "%";
      uploadNote(entry, "Uploading " + Math.round(event.loaded / event.total * 100) + "%");
    };
    xhr.onload = function () {
      uploading = false;
      var reply = {};
      try { reply = JSON.parse(xhr.responseText || "{}"); } catch (e) {}
      if (xhr.status >= 500 || xhr.status === 0) { entry.state = "queued"; retryUploadsLater(); return; }
      if (xhr.status >= 400) { finishUpload(nextId, reply.error || "Could not be sent."); pumpUploads(); return; }
      applyUploadStatus(reply);
      pumpUploads();
    };
    xhr.onerror = function () {   // offline or the server is down: keep it and try again later
      uploading = false;
      entry.state = "queued";
      uploadNote(entry, "Waiting for the connection…");
      retryUploadsLater();
    };
    xhr.send(data);
  }
  var uploadRetryTimer = null;
  function retryUploadsLater() {
    if (uploadRetryTimer) return;
    uploadRetryTimer = window.setTimeout(function () { uploadRetryTimer = null; pumpUploads(); }, 5000);
  }
  function applyUploadStatus(reply) {
    var entry = uploads[reply.client_id];
    if (!entry) return;
    if (reply.status === "FAILED") { finishUpload(reply.client_id, reply.error || "Could not be sent."); return; }
    if (reply.status === "READY") {
      entry.state = "done";
      dbDelete(reply.client_id);
      delete uploads[reply.client_id];
      if (!known[reply.message_id]) catchUp();   // the live push may have been missed
      return;
    }
    entry.state = "processing";
    var bar = entry.node.querySelector(".chat-upload-progress");
    if (bar) bar.remove();
    uploadNote(entry, (entry.item.isVideo ? "Video" : "Photo") + " · processing…");
  }
  // Fallback check for uploads still processing (in case a live update was missed).
  window.setInterval(function () {
    if (!uploadForm || !window.fetch) return;
    var ids = Object.keys(uploads).filter(function (id) { return uploads[id].state === "processing"; });
    if (!ids.length) return;
    getJson(uploadForm.getAttribute("data-status-url") + "?ids=" + ids.join(",")).then(function (data) {
      (data.uploads || []).forEach(applyUploadStatus);
    }).catch(function () {});
  }, 4000);
  if (fileInput) {
    fileInput.addEventListener("change", function () {
      if (!atLatest) jumpToLatest();
      queueFiles(fileInput.files);
      fileInput.value = "";
    });
  }
  // Uploads left from an earlier visit (reload, closed tab) continue by themselves.
  if (uploadForm) {
    dbMine().then(function (items) {
      (items || []).forEach(function (item) {
        if (uploads[item.id]) return;
        uploads[item.id] = { item: item, node: mediaBubble(item), state: "queued" };
      });
      pumpUploads();
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
      if (typeof pumpUploads === "function") pumpUploads();
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
      if (data.type === "event" && data.event === "attachment_failed" && String(data.uploader_id) === userId) {
        finishUpload(data.client_id, data.error || "Could not be sent.");
      }
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

// v2.1.0 DES-007 — Messenger-style chat bar: one ＋ button with a small menu
// (Photo or video · Ownership questions for the finder), a message field that grows, and Send.
document.addEventListener("DOMContentLoaded", function () {
  var plus = document.querySelector(".chat-plus");
  var menu = document.getElementById("chat-plus-menu");
  var fileInput = document.getElementById("chat-file");
  var ask = document.getElementById("question-ask");
  var input = document.getElementById("chat-input");
  var embedded = document.body.getAttribute("data-embed") === "true" && window.parent !== window;

  function items() { return menu ? Array.prototype.slice.call(menu.querySelectorAll("[role=menuitem]")) : []; }
  function isOpen() { return menu && !menu.hidden; }
  function openMenu() {
    if (!menu || !plus) return;
    menu.hidden = false;
    plus.setAttribute("aria-expanded", "true");
    plus.classList.remove("chat-plus--hint");
    var first = items()[0];
    if (first) first.focus();
  }
  function closeMenu(returnFocus) {
    if (!isOpen()) return;
    menu.hidden = true;
    plus.setAttribute("aria-expanded", "false");
    if (returnFocus) plus.focus();
  }
  function openQuestions() {
    closeMenu(false);
    if (!ask) return;
    ask.open = true;
    ask.scrollIntoView({ block: "nearest", behavior: "smooth" });
    var filter = ask.querySelector(".question-filter");
    if (filter) window.setTimeout(function () { filter.focus({ preventScroll: true }); }, 150);
  }

  if (plus && menu) {
    plus.addEventListener("click", function () { if (isOpen()) closeMenu(true); else openMenu(); });
    menu.addEventListener("keydown", function (event) {
      var list = items(), at = list.indexOf(document.activeElement);
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        var next = list[(at + (event.key === "ArrowDown" ? 1 : list.length - 1)) % list.length];
        if (next) next.focus();
      } else if (event.key === "Tab") {
        closeMenu(false);
      }
    });
    var mediaItem = menu.querySelector("[data-plus-media]");
    if (mediaItem && fileInput) mediaItem.addEventListener("click", function () { closeMenu(false); fileInput.click(); plus.focus(); });
    document.addEventListener("click", function (event) {
      if (isOpen() && !menu.contains(event.target) && !plus.contains(event.target)) closeMenu(false);
    });
  }
  // "＋ → Ownership questions" links in the hint lines (they can be redrawn live, so listen on the page).
  document.addEventListener("click", function (event) {
    var opener = event.target.closest && event.target.closest("[data-open-questions]");
    if (opener) { event.preventDefault(); openQuestions(); }
  });
  if (ask && window.location.hash === "#question-ask") ask.open = true;

  // The message field grows with the text (up to about 6 lines), like Messenger.
  if (input) {
    var grow = function () {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight + 2, window.innerHeight * 0.3) + "px";
    };
    input.addEventListener("input", grow);
    var form = document.getElementById("chat-form");
    if (form) form.addEventListener("submit", function () { window.setTimeout(grow, 0); });
  }

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    if (isOpen()) { closeMenu(true); return; }
    if (ask && ask.open && ask.contains(document.activeElement)) { ask.open = false; if (plus) plus.focus(); return; }
    // Inside the chat window on a post page: Esc closes the window.
    if (embedded && !(event.target.closest && event.target.closest("#chat-search-input"))) {
      window.parent.postMessage({ type: "findit-chat-close" }, window.location.origin);
    }
  });

  // Inside the chat window: ordinary links open in the main window (the chat window is only for the chat).
  if (embedded) {
    document.addEventListener("click", function (event) {
      var link = event.target.closest && event.target.closest("a[href]");
      if (!link || link.target || link.getAttribute("href").charAt(0) === "#") return;
      link.target = "_top";
    });
  }
});
