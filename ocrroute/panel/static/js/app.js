/* OcrRoute panel — theme, language, live status, small UX helpers */
(function () {
  "use strict";

  function setCookie(name, value, days) {
    var max = days ? "; max-age=" + days * 86400 : "";
    document.cookie = name + "=" + encodeURIComponent(value) + max + "; path=/; samesite=lax";
  }

  function applyTheme(theme) {
    if (theme !== "light" && theme !== "dark" && theme !== "system") theme = "system";
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("ocrroute-theme", theme);
    } catch (e) {}
    setCookie("ocrroute_theme", theme, 365);
    var sel = document.getElementById("theme-select");
    if (sel && sel.value !== theme) sel.value = theme;
  }

  function setTheme(theme) {
    applyTheme(theme);
    var next = location.pathname + location.search;
    if (next.indexOf("/panel") !== 0) next = "/panel/";
    location.href = "/panel/prefs?theme=" + encodeURIComponent(theme) + "&next=" + encodeURIComponent(next);
  }

  function setLang(code) {
    try {
      localStorage.setItem("ocrroute-lang", code);
    } catch (e) {}
    setCookie("ocrroute_lang", code, 365);
    var next = location.pathname + location.search;
    if (next.indexOf("/panel") !== 0) next = "/panel/";
    location.href = "/panel/prefs?lang=" + encodeURIComponent(code) + "&next=" + encodeURIComponent(next);
  }

  function previewFile(input) {
    var f = input && input.files && input.files[0];
    var img = document.getElementById("pg-preview");
    if (!f || !img) return;
    if (f.type && f.type.indexOf("image/") === 0) {
      img.src = URL.createObjectURL(f);
      img.alt = f.name || "preview";
    } else {
      img.removeAttribute("src");
      img.alt = f.name || "file";
    }
  }

  function filterCards(q) {
    q = (q || "").toLowerCase();
    var cards = document.querySelectorAll("#engine-grid .engine");
    for (var i = 0; i < cards.length; i++) {
      var name = (cards[i].getAttribute("data-name") || "").toLowerCase();
      cards[i].style.display = !q || name.indexOf(q) >= 0 ? "" : "none";
    }
  }

  // Boot theme from localStorage if present (faster than waiting for cookie roundtrip)
  try {
    var stored = localStorage.getItem("ocrroute-theme");
    if (stored) applyTheme(stored);
  } catch (e) {}

  // Live status pill via SSE
  try {
    var es = new EventSource("/panel/stream");
    var el = document.getElementById("server-status");
    es.onmessage = function () {
      if (!el) return;
      el.textContent = el.getAttribute("data-live") || "Live";
      el.classList.remove("offline");
    };
    es.onerror = function () {
      if (!el) return;
      el.textContent = el.getAttribute("data-offline") || "Offline";
      el.classList.add("offline");
    };
  } catch (e) {}

  window.OcrRouteUI = {
    setTheme: setTheme,
    setLang: setLang,
    applyTheme: applyTheme,
    previewFile: previewFile,
    filterCards: filterCards,
  };
})();
