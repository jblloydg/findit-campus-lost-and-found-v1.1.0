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

  // Item photo: preview the chosen image before submitting, and check its
  // type and size early. The server still validates every upload.
  var photoInput = document.querySelector("[data-photo-input]");
  var photoPreview = document.querySelector("[data-photo-preview]");
  var photoError = document.querySelector("[data-photo-error]");
  var photoCurrent = document.querySelector("[data-photo-current]");
  var removePhoto = document.querySelector("input[name='remove_photo']");
  var previewUrl = null;
  var allowedPhotoTypes = ["image/jpeg", "image/png", "image/webp"];
  var maxPhotoBytes = 5 * 1024 * 1024;

  function showPhotoError(text) {
    if (!photoError) return;
    photoError.textContent = text || "";
    photoError.hidden = !text;
  }
  function clearPreview() {
    if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
    if (photoPreview) photoPreview.hidden = true;
    if (photoCurrent) photoCurrent.classList.remove("is-replaced");
  }
  if (photoInput && photoPreview) {
    var previewImage = photoPreview.querySelector("img");
    var previewName = photoPreview.querySelector("[data-photo-name]");
    photoInput.addEventListener("change", function () {
      clearPreview();
      showPhotoError("");
      var file = photoInput.files && photoInput.files[0];
      if (!file) return;
      if (file.type && allowedPhotoTypes.indexOf(file.type) === -1) {
        showPhotoError("Upload a JPG, PNG, or WebP exterior photo.");
        photoInput.value = "";
        return;
      }
      if (file.size > maxPhotoBytes) {
        showPhotoError("Choose an image smaller than 5 MB.");
        photoInput.value = "";
        return;
      }
      previewUrl = URL.createObjectURL(file);
      previewImage.src = previewUrl;
      if (previewName) previewName.textContent = file.name;
      photoPreview.hidden = false;
      if (photoCurrent) photoCurrent.classList.add("is-replaced");
      if (removePhoto) removePhoto.checked = false;
    });
    var clearButton = photoPreview.querySelector("[data-photo-clear]");
    if (clearButton) {
      clearButton.addEventListener("click", function () {
        photoInput.value = "";
        clearPreview();
      });
    }
  }
  if (removePhoto && photoCurrent) {
    removePhoto.addEventListener("change", function () {
      photoCurrent.classList.toggle("is-removed", removePhoto.checked);
      if (removePhoto.checked && photoInput && photoInput.value) {
        photoInput.value = "";
        clearPreview();
      }
    });
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
