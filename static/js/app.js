document.addEventListener("DOMContentLoaded", function () {
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

  if (document.body.getAttribute("data-user-authenticated") === "true") {
    var noticeSocket = new WebSocket(
      (window.location.protocol === "https:" ? "wss:" : "ws:") + "//" + window.location.host + "/ws/notifications/"
    );
    noticeSocket.addEventListener("message", function (event) {
      var data;
      try { data = JSON.parse(event.data); } catch (error) { return; }
      if (data.type !== "notification") return;
      var badge = document.querySelector(".notice-count");
      var nav = document.querySelector(".nav-notice");
      if (!badge && nav) {
        badge = document.createElement("span");
        badge.className = "notice-count";
        nav.appendChild(badge);
      }
      if (badge) badge.textContent = String((parseInt(badge.textContent || "0", 10) || 0) + 1);
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
      flash.textContent = data.text;
      stack.appendChild(flash);
      window.setTimeout(function () { flash.remove(); }, 6500);
    });
  }

  var typeSelect = document.querySelector("[data-post-type]");
  var questionBlock = document.getElementById("verification-questions");
  function updateQuestions() {
    if (!typeSelect || !questionBlock) return;
    var isFound = typeSelect.value === "FOUND";
    questionBlock.hidden = !isFound;
    questionBlock.querySelectorAll("input,textarea").forEach(function (input) {
      input.required = isFound;
    });
  }
  if (typeSelect) {
    typeSelect.addEventListener("change", updateQuestions);
    updateQuestions();
  }

  var params = new URLSearchParams(window.location.search);
  if (params.get("resume") === "claim") {
    var claim = document.getElementById("claim-form");
    if (claim) {
      claim.scrollIntoView({ behavior: "smooth", block: "center" });
      var firstAnswer = claim.querySelector("textarea");
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
