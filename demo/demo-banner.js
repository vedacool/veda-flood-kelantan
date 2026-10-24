// VEDA public demo: the proxy adds this to VEDA's two pages (demo/nginx.conf). It never changes the app's own code.
// - the demo banner follows the page's language (EN | BM): the main page sets <html lang>, /live keeps "veda.lang"
// - under each answer: a link to the feedback form, in the same language
(function () {
  "use strict";
  var WORDS = {
    en: { note: "Demo · past flood replay · not live · not an official warning", feedback: "Feedback",
          ask: "Was this clear? 1-minute feedback ›" },
    ms: { note: "Demo · ulang tayang banjir lalu · bukan data semasa · bukan amaran rasmi", feedback: "Maklum balas",
          ask: "Jelas tak? Maklum balas 1 minit ›" }
  };
  var answer = document.getElementById("s-answer");          // only the main page has answers

  function lang() {
    if (answer) return (document.documentElement.lang || "").indexOf("ms") === 0 ? "ms" : "en";
    try { return localStorage.getItem("veda.lang") === "ms" ? "ms" : "en"; } catch (e) { return "en"; }
  }

  var ask = null;
  if (answer) {
    ask = document.createElement("a");
    ask.id = "veda-demo-ask";
    ask.style.cssText = "display:flex;align-items:center;justify-content:center;min-height:44px;margin-top:12px;" +
      "color:inherit;text-decoration:underline";
    var again = document.getElementById("a-again");
    if (again && again.parentNode === answer) answer.insertBefore(ask, again); else answer.appendChild(ask);
  }

  function apply() {
    var l = lang(), w = WORDS[l], q = l === "ms" ? "/feedback?lang=ms" : "/feedback?lang=en";
    var banner = document.getElementById("veda-demo-banner");
    if (banner) {
      banner.lang = l;
      banner.querySelector("span").textContent = w.note;
      var link = banner.querySelector("a");
      link.textContent = w.feedback;
      link.href = q;
    }
    if (ask) { ask.lang = l; ask.textContent = w.ask; ask.href = q; }
  }

  apply();
  new MutationObserver(apply).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
  window.addEventListener("storage", function (e) { if (e.key === "veda.lang") apply(); });
})();
