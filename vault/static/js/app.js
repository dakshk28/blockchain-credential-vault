// Progressive enhancements. Every page works without JavaScript.
(function () {
  "use strict";
  var root = document.documentElement;

  // Theme toggle: cycles to the opposite of what is currently shown and remembers it.
  function currentTheme() {
    var set = root.getAttribute("data-theme");
    if (set) return set;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("acv-theme", next); } catch (e) {}
    });
  });

  // Mobile sidebar.
  var sidebar = document.querySelector(".sidebar"), scrim = document.querySelector(".scrim");
  function setMenu(open) {
    if (!sidebar) return;
    sidebar.classList.toggle("open", open);
    if (scrim) scrim.classList.toggle("open", open);
  }
  document.querySelectorAll("[data-menu-toggle]").forEach(function (b) { b.addEventListener("click", function () { setMenu(!sidebar.classList.contains("open")); }); });
  if (scrim) scrim.addEventListener("click", function () { setMenu(false); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") setMenu(false); });

  // Toasts: dismiss on click, auto-hide non-errors.
  document.querySelectorAll(".toast").forEach(function (toast) {
    function hide() { toast.classList.add("hide"); setTimeout(function () { toast.remove(); }, 320); }
    var close = toast.querySelector(".close");
    if (close) close.addEventListener("click", hide);
    if (!toast.classList.contains("toast-error")) setTimeout(hide, 6000);
  });

  // Drop zones: show the chosen file and support drag-and-drop styling.
  document.querySelectorAll(".dropzone").forEach(function (zone) {
    var input = zone.querySelector("input[type=file]"), label = zone.querySelector(".file-name");
    if (!input) return;
    function update() {
      var file = input.files && input.files[0];
      zone.classList.toggle("has-file", !!file);
      if (label) label.textContent = file ? file.name + " · " + Math.max(1, Math.round(file.size / 1024)) + " KB" : label.getAttribute("data-empty");
    }
    input.addEventListener("change", update);
    ["dragenter", "dragover"].forEach(function (t) { zone.addEventListener(t, function () { zone.classList.add("dragover"); }); });
    ["dragleave", "drop"].forEach(function (t) { zone.addEventListener(t, function () { zone.classList.remove("dragover"); }); });
  });

  // Copy-to-clipboard buttons: <button data-copy="text">.
  document.querySelectorAll("[data-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      var text = button.getAttribute("data-copy"), original = button.innerHTML;
      function done() { button.textContent = "Copied"; setTimeout(function () { button.innerHTML = original; }, 1500); }
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () {});
    });
  });

  // Confirmation for destructive forms: <form data-confirm="Are you sure?">.
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) { if (!window.confirm(form.getAttribute("data-confirm"))) e.preventDefault(); });
  });

  // Password strength meter: <input data-strength> followed by .password-meter span.
  document.querySelectorAll("input[data-strength]").forEach(function (input) {
    var bar = input.parentElement.querySelector(".password-meter span");
    if (!bar) return;
    input.addEventListener("input", function () {
      var v = input.value, score = 0;
      if (v.length >= 12) score++;
      if (/\d/.test(v)) score++;
      if (/[a-z]/.test(v) && /[A-Z]/.test(v)) score++;
      if (/[^A-Za-z0-9]/.test(v)) score++;
      if (v.length >= 16) score++;
      var colors = ["var(--danger)", "var(--danger)", "var(--warning)", "var(--warning)", "var(--success)", "var(--success)"];
      bar.style.width = (score / 5 * 100) + "%";
      bar.style.background = colors[score];
    });
  });
})();

// Credential templates prefill the issue form: <select data-template-select> options carry data-title etc.
document.querySelectorAll("[data-template-select]").forEach(function (select) {
  select.addEventListener("change", function () {
    var option = select.options[select.selectedIndex], form = select.form;
    ["title", "programme", "description"].forEach(function (field) {
      var value = option.getAttribute("data-" + field), input = form.elements[field];
      if (input && value !== null) input.value = value;
    });
  });
});

// Upload-or-generate switch on the issue form: shows the fields for the chosen mode.
document.querySelectorAll("[data-mode-switch]").forEach(function (switcher) {
  var form = switcher.form || switcher.closest("form");
  function apply() {
    var mode = form.querySelector("input[name=document_mode]:checked").value;
    form.querySelectorAll("[data-mode]").forEach(function (el) { el.hidden = el.getAttribute("data-mode") !== mode; });
  }
  switcher.addEventListener("change", apply); apply();
});

document.querySelectorAll("[data-print]").forEach(function (button) { button.addEventListener("click", function () { window.print(); }); });
