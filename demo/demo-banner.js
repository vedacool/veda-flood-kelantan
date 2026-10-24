// VEDA public demo: the proxy adds this to VEDA's pages (demo/nginx.conf). It never changes the app's own code.
// Under each answer: a link to the feedback form, in the page's language (<html lang>, set by the page).
// The demo strip, top bar and footer come from the app's shared frame (B-96, app/frame.py) - not from here.
(function () {
  "use strict";
  var WORDS = {
    en: { ask: "Was this clear? 1-minute feedback ›" },
    ms: { ask: "Jelas tak? Maklum balas 1 minit ›" }
  };
  var answer = document.getElementById("s-answer");          // only the main page has answers
  if (!answer) return;

  function lang() { return (document.documentElement.lang || "").indexOf("ms") === 0 ? "ms" : "en"; }

  var ask = document.createElement("a");
  ask.id = "veda-demo-ask";
  ask.style.cssText = "display:flex;align-items:center;justify-content:center;min-height:44px;margin-top:12px;" +
    "color:inherit;text-decoration:underline";
  var again = document.getElementById("a-again");
  if (again && again.parentNode === answer) answer.insertBefore(ask, again); else answer.appendChild(ask);

  function apply() {
    var l = lang();
    ask.lang = l; ask.textContent = WORDS[l].ask; ask.href = "/feedback?lang=" + l;
  }

  apply();
  new MutationObserver(apply).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
})();
