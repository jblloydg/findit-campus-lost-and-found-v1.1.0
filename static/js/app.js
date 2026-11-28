document.addEventListener("DOMContentLoaded", function () {
  // One-time key per form (duplicate-submit protection) and single-click submit buttons.
  function oneTimeKey() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return String(Date.now()) + "-" + Math.random().toString(16).slice(2);
  }
  document.querySelectorAll("form").forEach(function (form) {
    if ((form.getAttribute("method") || "").toLowerCase() !== "post") return;
    var key = document.createElement("input");
    key.type = "hidden";
    key.name = "idempotency_key";
    key.value = oneTimeKey();
    form.appendChild(key);
    form.addEventListener("submit", function () {
      if (form.getAttribute("data-submitting") === "true") return;
      form.setAttribute("data-submitting", "true");
      window.setTimeout(function () {
        form.querySelectorAll("button[type='submit'], button:not([type])").forEach(function (b) { b.disabled = true; });
      }, 0);
    });
  });

  var modal = document.getElementById("login-modal");
  var nextField = document.getElementById("login-next");
  var firstInput = modal ? modal.querySelector("input[name='username']") : null;

  function openLogin(nextUrl) {
    if (!modal) return;
    if (nextField) nextField.value = nextUrl || window.location.pathname + window.location.search;
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
    if (firstInput) firstInput.focus();
  }

  function closeLogin() {
    if (!modal) return;
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
  }

  document.querySelectorAll("[data-login-next]").forEach(function (button) {
    button.addEventListener("click", function (event) {
      event.preventDefault();
      openLogin(button.getAttribute("data-login-next"));
    });
  });
  document.querySelectorAll("[data-close-login]").forEach(function (button) {
    button.addEventListener("click", closeLogin);
  });
  if (modal) {
    modal.addEventListener("click", function (event) {
      if (event.target === modal) closeLogin();
    });
  }
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeLogin();
  });

  // Live notifications (v1.1.1, CHG-004). The saved notifications on the server are the queue:
  // on every (re)connect the server sends the true unread counts, the browser asks for any
  // notices it missed, and each notice id is shown only once (no double counting).
  if (document.body.getAttribute("data-user-authenticated") === "true" && window.WebSocket && document.body.getAttribute("data-embed") !== "true") {
    var noticeUrl = (window.location.protocol === "https:" ? "wss:" : "ws:") + "//" + window.location.host + "/ws/notifications/";
    var seenKey = "findit-seen-notices-" + document.body.getAttribute("data-user-id");
    var seen = {};
    try { (JSON.parse(window.sessionStorage.getItem(seenKey) || "[]")).forEach(function (id) { seen[id] = true; }); } catch (e) {}
    var lastId = null;
    var noticeDelay = 1000;
    var remember = function (id) {
      seen[id] = true;
      try { window.sessionStorage.setItem(seenKey, JSON.stringify(Object.keys(seen).slice(-200))); } catch (e) {}
    };
    // v2.0.0: the same count can show in the sidebar and in the top bar, so update every copy.
    var setBadge = function (selector, navSelector, count) {
      var navs = document.querySelectorAll(navSelector);
      for (var n = 0; n < navs.length; n++) {
        if (!navs[n].querySelector(selector) && count > 0) {
          var made = document.createElement("span");
          made.className = selector.slice(1);
          navs[n].appendChild(made);
        }
      }
      var badges = document.querySelectorAll(selector);
      for (var b = 0; b < badges.length; b++) { badges[b].textContent = String(count); badges[b].hidden = count <= 0; }
    };
    var currentCount = function (selector) {
      var badge = document.querySelector(selector);
      return badge && !badge.hidden ? (parseInt(badge.textContent || "0", 10) || 0) : 0;
    };
    var flashNotice = function (text) {
      var stack = document.querySelector(".flash-stack");
      if (!stack) {
        stack = document.createElement("div");
        stack.className = "flash-stack";
        stack.setAttribute("role", "status");
        stack.setAttribute("aria-live", "polite");
        document.body.appendChild(stack);
      }
      var flash = document.createElement("div");
      flash.className = "flash flash-info";
      flash.textContent = text;
      stack.appendChild(flash);
      window.setTimeout(function () { flash.remove(); }, 6500);
    };
    var noticeSocket = null;
    var connectNotices = function () {
      var socket;
      try { socket = new WebSocket(noticeUrl); } catch (e) { return; }
      noticeSocket = socket;
      socket.addEventListener("open", function () { noticeDelay = 1000; });
      socket.addEventListener("message", function (event) {
        var data;
        try { data = JSON.parse(event.data); } catch (error) { return; }
        if (data.type === "sync") {
          setBadge(".notice-count", ".nav-notice", data.unread || 0);
          setBadge(".priority-count", ".nav-messages", data.priority || 0);
          if (lastId !== null && data.latest_id > lastId) socket.send(JSON.stringify({ type: "since", after_id: lastId }));
          lastId = data.latest_id || 0;
          return;
        }
        if (data.type !== "notification" || !data.id) return;
        if (lastId === null || data.id > lastId) lastId = data.id;
        if (seen[data.id]) return;  // already shown: never count twice
        remember(data.id);
        if (!data.catch_up) {
          setBadge(".notice-count", ".nav-notice", currentCount(".notice-count") + 1);
          if (data.priority) setBadge(".priority-count", ".nav-messages", currentCount(".priority-count") + 1);
        }
        flashNotice(data.text);
      });
      socket.addEventListener("close", function (event) {
        if (event.code === 4403) return;
        window.setTimeout(function () { if (noticeSocket === socket) connectNotices(); }, noticeDelay);
        noticeDelay = Math.min(noticeDelay * 2, 10000);
      });
    };
    var noticesNow = function () {
      if (noticeSocket && noticeSocket.readyState === WebSocket.CLOSED) { noticeDelay = 1000; connectNotices(); }
    };
    window.setInterval(function () {
      if (noticeSocket && noticeSocket.readyState === WebSocket.OPEN) noticeSocket.send(JSON.stringify({ type: "sync" }));
    }, 60000);
    window.addEventListener("online", noticesNow);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) noticesNow(); });
    connectNotices();
  }

  var typeSelect = document.querySelector("[data-post-type]");
  var categorySelect = document.querySelector("[data-category]");
  var questionBlock = document.getElementById("verification-questions");
  var questionList = document.getElementById("question-list");
  var questionSearch = document.getElementById("question-search");
  var pickedLabel = document.getElementById("question-picked");
  var suggestNote = document.getElementById("question-suggest-note");
  var MAX_QUESTIONS = 5;

  function updateQuestions() {
    if (!typeSelect || !questionBlock) return;
    questionBlock.hidden = typeSelect.value !== "FOUND";
    // BUG-020: the sidebar highlights "Report lost item" or "Report found item" to match the chosen type.
    Array.prototype.forEach.call(document.querySelectorAll("[data-report-kind]"), function (link) {
      var on = link.getAttribute("data-report-kind") === typeSelect.value;
      link.classList.toggle("is-active", on);
      if (on) { link.setAttribute("aria-current", "page"); } else { link.removeAttribute("aria-current"); }
    });
  }
  function questionOptions() {
    return questionList ? Array.prototype.slice.call(questionList.querySelectorAll(".question-option")) : [];
  }
  function updatePicked() {
    var options = questionOptions();
    var checked = options.filter(function (o) { return o.querySelector("input").checked; });
    options.forEach(function (o) {
      var box = o.querySelector("input");
      o.classList.toggle("is-checked", box.checked);
      box.disabled = !box.checked && checked.length >= MAX_QUESTIONS;
    });
    if (pickedLabel) {
      var n = checked.length;
      pickedLabel.textContent = n + " of " + MAX_QUESTIONS + " picked" + (n < 3 ? " · " + (3 - n) + " default" + (3 - n === 1 ? "" : "s") + " will be added" : "");
    }
  }
  function sortByCategory() {
    if (!questionList) return;
    var categoryId = categorySelect ? categorySelect.value : "";
    var options = questionOptions();
    var anySuggested = false;
    options.forEach(function (o) {
      var ids = (o.getAttribute("data-categories") || "").split(" ");
      var suggested = !!categoryId && ids.indexOf(categoryId) !== -1;
      o.classList.toggle("is-suggested", suggested);
      if (suggested) anySuggested = true;
    });
    options.sort(function (a, b) {
      var rank = function (o) { return o.classList.contains("is-suggested") ? 0 : (o.getAttribute("data-general") === "1" ? 1 : 2); };
      return rank(a) - rank(b);
    }).forEach(function (o) { questionList.insertBefore(o, document.getElementById("question-empty")); });
    if (suggestNote) suggestNote.hidden = !anySuggested;
  }
  function filterQuestions() {
    var term = questionSearch ? questionSearch.value.trim().toLowerCase() : "";
    var shown = 0;
    questionOptions().forEach(function (o) {
      var match = !term || o.textContent.toLowerCase().indexOf(term) !== -1;
      o.hidden = !match;
      if (match) shown += 1;
    });
    var empty = document.getElementById("question-empty");
    if (empty) empty.hidden = shown !== 0;
  }
  if (typeSelect) {
    typeSelect.addEventListener("change", updateQuestions);
    updateQuestions();
  }
  if (questionList) {
    questionList.addEventListener("change", updatePicked);
    if (questionSearch) {
      questionSearch.addEventListener("input", filterQuestions);
      questionSearch.addEventListener("keydown", function (event) { if (event.key === "Enter") event.preventDefault(); });
    }
    if (categorySelect) categorySelect.addEventListener("change", sortByCategory);
    sortByCategory();
    updatePicked();
  }

  var photoInput = document.querySelector("input[type='file'][name='photos']");
  var humanCheck = document.getElementById("human-check");
  var photoCount = document.getElementById("photo-count");
  function updatePhotoState() {
    if (!photoInput) return;
    var existing = humanCheck ? parseInt(humanCheck.getAttribute("data-existing") || "0", 10) : 0;
    var removing = document.querySelectorAll("input[name='remove_photos']:checked").length;
    var adding = photoInput.files ? photoInput.files.length : 0;
    var total = existing - removing + adding;
    if (photoCount) photoCount.textContent = total ? total + " of 20 photos" + (total > 20 ? " — remove some to continue" : "") : "";
    if (humanCheck) {
      var threshold = parseInt(humanCheck.getAttribute("data-threshold") || "10", 10);
      var needed = adding > 0 && total > threshold;
      humanCheck.hidden = !needed && !humanCheck.querySelector(".field-error");
      var answer = humanCheck.querySelector("input[type='text']");
      if (answer) answer.required = needed;
    }
  }
  if (photoInput) {
    photoInput.addEventListener("change", updatePhotoState);
    document.querySelectorAll("input[name='remove_photos']").forEach(function (box) { box.addEventListener("change", updatePhotoState); });
    updatePhotoState();
  }

  // Search + max-count for the in-chat question picker.
  // CHG-011: the finder's hint link "＋ Questions" opens the question box it jumps to.
  document.querySelectorAll('a[href="#question-ask"]').forEach(function (link) {
    link.addEventListener("click", function () { var box = document.getElementById("question-ask"); if (box) box.open = true; });
  });
  document.querySelectorAll(".question-ask").forEach(function (box) {
    var filter = box.querySelector(".question-filter");
    var list = box.querySelector(".chat-question-list");
    if (!list) return;
    var max = parseInt(list.getAttribute("data-max") || "5", 10);
    var items = Array.prototype.slice.call(list.querySelectorAll(".question-option"));
    function sync() {
      var checked = items.filter(function (o) { return o.querySelector("input").checked; }).length;
      items.forEach(function (o) {
        var input = o.querySelector("input");
        o.classList.toggle("is-checked", input.checked);
        input.disabled = !input.checked && checked >= max;
      });
    }
    list.addEventListener("change", sync);
    if (filter) {
      filter.addEventListener("keydown", function (event) { if (event.key === "Enter") event.preventDefault(); });
      filter.addEventListener("input", function () {
        var term = filter.value.trim().toLowerCase();
        items.forEach(function (o) { o.hidden = !!term && o.textContent.toLowerCase().indexOf(term) === -1; });
      });
    }
    sync();
  });

  var params0 = new URLSearchParams(window.location.search);
  // Copy link (share mode). Server marks the post as shared, then the link is copied.
  document.querySelectorAll("[data-share-form]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.fetch) return;
      event.preventDefault();
      var url = form.getAttribute("data-share-url");
      var linkBox = form.parentNode.querySelector(".share-link");
      fetch(form.action, { method: "POST", body: new FormData(form), credentials: "same-origin", headers: { "x-requested-with": "fetch" } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          url = data.url || url;
          var count = document.getElementById("share-count");
          if (count) count.textContent = "Shared by " + data.share_count + (data.share_count === 1 ? " person" : " people");
          var done = function () { var b = form.querySelector("button"); if (b) { b.textContent = "Link copied"; b.disabled = false; } };
          if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(url).then(done, function () { if (linkBox) { linkBox.hidden = false; linkBox.select(); } });
          } else if (linkBox) { linkBox.hidden = false; linkBox.select(); done(); }
          form.removeAttribute("data-submitting");
          var key = form.querySelector("input[name='idempotency_key']");
          if (key) key.value = oneTimeKey();
        })
        .catch(function () { form.submit(); });
    });
  });

  // Closed-listing pop-up.
  document.querySelectorAll("[data-close-closed]").forEach(function (btn) {
    btn.addEventListener("click", function () { var m = document.getElementById("closed-modal"); if (m) m.classList.remove("is-open"); });
  });

  // DES-007 (v2.1.0): the chat opens in a big window over the post page. The address bar shows the
  // chat's own link (/conversations/<id>/) while it is open, so the chat has its usual address (for
  // example for a moderator's review). ×, Esc, a tap outside or the Back button close it, and the
  // post page is still where the person left it. Without JavaScript every link opens the full chat page.
  var overlay = document.getElementById("chat-overlay");
  if (overlay && window.history && window.history.pushState) {
    var frame = overlay.querySelector("iframe");
    var postUrl = window.location.pathname + window.location.search;
    var chatPath = /^\/conversations\/[0-9a-f-]+\/$/;
    var lastFocus = null, pushedUrl = null, frameChat = null;
    var openChat = function (url) {
      lastFocus = document.activeElement;
      overlay.hidden = false;
      document.body.classList.add("chat-overlay-open");
      var target = url.split("#")[0];
      if (frameChat && target === frameChat) {
        showChatAddress(frameChat);               // already loaded: just show it again
      } else {
        overlay.classList.add("is-loading");
        frame.src = target + (target.indexOf("?") === -1 ? "?" : "&") + "embed=1";
      }
      var close = overlay.querySelector(".chat-overlay-close");
      if (close) close.focus();
    };
    var showChatAddress = function (path) {
      if (window.location.pathname !== path) { window.history.pushState({ finditChat: path }, "", path); pushedUrl = path; }
    };
    var closeChat = function (fromBack) {
      if (overlay.hidden) return;
      overlay.hidden = true;
      document.body.classList.remove("chat-overlay-open");
      if (!fromBack && pushedUrl && window.location.pathname === pushedUrl) { pushedUrl = null; window.history.back(); }
      else if (window.location.pathname + window.location.search !== postUrl) window.history.replaceState(null, "", postUrl);
      pushedUrl = null;
      if (lastFocus && lastFocus.focus) lastFocus.focus();
    };
    frame.addEventListener("load", function () {
      overlay.classList.remove("is-loading");
      var where;
      try { where = frame.contentWindow.location; } catch (e) { return; }
      if (!where || where.href === "about:blank") return;
      if (chatPath.test(where.pathname)) {
        frameChat = where.pathname;
        if (!overlay.hidden) showChatAddress(frameChat);
      } else {
        // The chat could not be opened (e.g. blocked, or the post closed): show that page normally.
        window.location.href = where.pathname + where.search;
      }
    });
    document.addEventListener("click", function (event) {
      var opener = event.target.closest && event.target.closest("[data-chat-open], [data-chat-start], [data-chat-url]");
      if (opener && !event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) {
        event.preventDefault();
        openChat(opener.getAttribute("data-chat-url") || opener.getAttribute("href"));
        return;
      }
      if (event.target.closest && event.target.closest("[data-chat-close]")) closeChat(false);
    });
    document.addEventListener("keydown", function (event) { if (event.key === "Escape" && !overlay.hidden) closeChat(false); });
    window.addEventListener("message", function (event) {
      if (event.origin === window.location.origin && event.data && event.data.type === "findit-chat-close") closeChat(false);
    });
    window.addEventListener("popstate", function (event) {
      if (!overlay.hidden) { pushedUrl = null; closeChat(true); }
      else if (event.state && event.state.finditChat) openChat(event.state.finditChat);
    });
    if (params0.get("chat") === "open") {
      var launcher = document.querySelector("[data-chat-url]");
      if (launcher) openChat(launcher.getAttribute("data-chat-url"));
    }
  }

  // Turn-in QR: the SVG is already in the page, so it still shows without internet.
  document.querySelectorAll("[data-qr-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var box = document.getElementById("qr-box");
      if (!box) return;
      box.hidden = !box.hidden;
      btn.textContent = box.hidden ? "Show turn-in QR" : "Hide turn-in QR";
    });
  });

  // Session 2 idea, adapted to 1-20 photos: preview the chosen images and
  // warn early about type and size. The server still checks every upload.
  var multiPhotoInput = document.querySelector("input[type='file'][name='photos']");
  var previewGrid = document.getElementById("photo-preview-grid");
  var photoWarn = document.getElementById("photo-warning");
  var previewUrls = [];
  if (multiPhotoInput && previewGrid) {
    multiPhotoInput.addEventListener("change", function () {
      previewUrls.forEach(function (u) { URL.revokeObjectURL(u); });
      previewUrls = [];
      previewGrid.innerHTML = "";
      var problems = [];
      Array.prototype.forEach.call(multiPhotoInput.files || [], function (file) {
        if (file.type && ["image/jpeg", "image/png", "image/webp"].indexOf(file.type) === -1) { problems.push(file.name + " is not JPG, PNG or WebP"); return; }
        if (file.size > 5 * 1024 * 1024) { problems.push(file.name + " is larger than 5 MB"); return; }
        var url = URL.createObjectURL(file);
        previewUrls.push(url);
        var img = document.createElement("img");
        img.src = url;
        img.alt = "Preview of " + file.name;
        previewGrid.appendChild(img);
      });
      previewGrid.hidden = previewUrls.length === 0;
      if (photoWarn) { photoWarn.textContent = problems.join(" · "); photoWarn.hidden = problems.length === 0; }
    });
  }

  var params = new URLSearchParams(window.location.search);
  if (params.get("resume") === "claim") {
    var claim = document.getElementById("claim-form");
    if (claim) {
      claim.scrollIntoView({ behavior: "smooth", block: "center" });
      var firstAnswer = claim.querySelector("select, textarea");
      if (firstAnswer) firstAnswer.focus({ preventScroll: true });
    }
  }
  if (params.get("resume") === "comment") {
    var comment = document.querySelector(".comment-composer textarea");
    if (comment) {
      comment.focus({ preventScroll: true });
      comment.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  var dismissible = document.querySelectorAll(".flash");
  dismissible.forEach(function (flash) {
    window.setTimeout(function () {
      flash.style.opacity = "0";
      flash.style.transition = "opacity .35s ease";
      window.setTimeout(function () { flash.remove(); }, 400);
    }, 5200);
  });
});

// Show/hide password buttons (account management feature)
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("input[data-password-toggle]").forEach(function (input) {
    var wrap = document.createElement("span");
    wrap.className = "password-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    var button = document.createElement("button");
    button.type = "button";
    button.className = "password-toggle";
    button.textContent = "Show";
    button.setAttribute("aria-label", "Show password");
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", function () {
      var showing = input.type === "text";
      input.type = showing ? "password" : "text";
      button.textContent = showing ? "Show" : "Hide";
      button.setAttribute("aria-label", showing ? "Show password" : "Hide password");
      button.setAttribute("aria-pressed", showing ? "false" : "true");
      input.focus();
    });
    wrap.appendChild(button);
  });

  // v2.0.0: on phones and tablets the sidebar is a drawer opened by the menu button.
  var drawerOpen = document.querySelector("[data-drawer-open]");
  var setDrawer = function (open) {
    document.body.classList.toggle("drawer-open", open);
    if (drawerOpen) drawerOpen.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) { var first = document.querySelector("#app-sidebar .nav-link"); if (first) first.focus(); }
    else if (drawerOpen && drawerOpen.offsetParent !== null) drawerOpen.focus();
  };
  if (drawerOpen) {
    drawerOpen.addEventListener("click", function () { setDrawer(true); });
    document.querySelectorAll("[data-drawer-close]").forEach(function (el) {
      el.addEventListener("click", function () { setDrawer(false); });
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && document.body.classList.contains("drawer-open")) setDrawer(false);
    });
  }

  // Close the profile dropdown when clicking elsewhere or pressing Escape.
  var menu = document.querySelector("[data-profile-menu]");
  if (menu) {
    document.addEventListener("click", function (event) {
      if (menu.open && !menu.contains(event.target)) menu.open = false;
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && menu.open) { menu.open = false; menu.querySelector("summary").focus(); }
    });
  }
});
