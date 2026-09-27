// Loaded synchronously in <head> so the saved theme applies before first paint (no flash).
(function () {
  try {
    var saved = localStorage.getItem("acv-theme");
    if (saved === "light" || saved === "dark") document.documentElement.setAttribute("data-theme", saved);
  } catch (e) { /* storage unavailable: follow the OS preference */ }
})();
