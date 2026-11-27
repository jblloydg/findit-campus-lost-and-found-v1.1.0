document.addEventListener("DOMContentLoaded", function () {
  var panel = document.getElementById("chat-messages");
  var form = document.getElementById("chat-form");
  var input = document.getElementById("chat-input");
  if (!panel) return;

  var conversationId = panel.getAttribute("data-conversation");
  var canSend = panel.getAttribute("data-can-send") === "true";
  var protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  var socket = new WebSocket(protocol + "//" + window.location.host + "/ws/conversations/" + conversationId + "/");
  var connectionText = document.getElementById("chat-status");
  var lastSent = { id: null, text: "" };

  function formatTime(value) {
    var date = new Date(value);
    return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  function addMessage(message) {
    if (panel.querySelector('[data-message-id="' + message.id + '"]')) return;
    var empty = panel.querySelector(".chat-empty");
    if (empty) empty.remove();
    var article = document.createElement("article");
    article.className = "chat-message" + (String(message.sender_id) === document.body.getAttribute("data-user-id") ? " mine" : "");
    article.setAttribute("data-message-id", message.id);
    var bubble = document.createElement("div");
    bubble.className = "message-bubble";
    var meta = document.createElement("div");
    meta.className = "message-meta";
    var name = document.createElement("strong");
    name.textContent = message.sender;
    var time = document.createElement("time");
    time.textContent = formatTime(message.sent_at);
    var text = document.createElement("p");
    text.textContent = message.text;
    meta.append(name, time);
    bubble.append(meta, text);
    article.appendChild(bubble);
    panel.appendChild(article);
    panel.scrollTop = panel.scrollHeight;
  }

  socket.addEventListener("open", function () {
    if (connectionText) connectionText.textContent = "Live chat connected.";
  });
  socket.addEventListener("message", function (event) {
    var data;
    try { data = JSON.parse(event.data); } catch (error) { return; }
    if (data.type === "message") {
      addMessage(data);
      if (data.client_id && data.client_id === lastSent.id) { lastSent = { id: null, text: "" }; if (connectionText) connectionText.textContent = ""; }
    }
    if (data.type === "event" && data.event === "question") refreshQuestions();
    if (data.type === "error") {
      if (connectionText) connectionText.textContent = data.message;
      // Not sent: give the text back so it is not lost.
      if (input && lastSent.text && (!data.client_id || data.client_id === lastSent.id) && !input.value) {
        input.value = lastSent.text;
      }
    }
  });
  socket.addEventListener("close", function () {
    if (connectionText) connectionText.textContent = "Live connection ended. Reload the page to reconnect.";
  });
  socket.addEventListener("error", function () {
    if (connectionText) connectionText.textContent = "Live chat could not connect. Check that the app server is running.";
  });

  function newId() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return String(Date.now()) + Math.random().toString(16).slice(2);
  }

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

  if (!form || !input) return;
  var pendingId = null;
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text || !canSend || socket.readyState !== WebSocket.OPEN) {
      if (connectionText && socket.readyState !== WebSocket.OPEN) connectionText.textContent = "Waiting for the live connection…";
      return;
    }
    // Same id for an accidental double send of the same text, so the server saves it once.
    if (!pendingId || form.getAttribute("data-last-text") !== text) pendingId = newId();
    form.setAttribute("data-last-text", text);
    lastSent = { id: pendingId, text: text };
    socket.send(JSON.stringify({ message: text, client_id: pendingId }));
    input.value = "";
    pendingId = null;
    input.focus();
  });
});
