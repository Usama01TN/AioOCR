/* OcrRoute panel enhancements */
(function () {
  // Theme from system if unset
  try {
    if (!localStorage.getItem("ocrroute-theme")) {
      // leave auto
    }
  } catch (e) {}

  // Live status pill via SSE
  try {
    var es = new EventSource("/panel/stream");
    es.onmessage = function () {
      var el = document.getElementById("server-status");
      if (el) el.textContent = "live";
    };
    es.onerror = function () {
      var el = document.getElementById("server-status");
      if (el) el.textContent = "offline";
    };
  } catch (e) {}
})();
