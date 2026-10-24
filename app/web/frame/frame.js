// B-96 shared frame: EN | BM for the top bar, demo strip and footer. The language is the one VEDA setting every page
// shares (localStorage "veda.lang"). A page that runs its own language switch sets window.vedaSetLang before this
// file loads (index.html does); otherwise this file switches the frame's words and reloads the page with ?lang=.
(function () {
  const store = { get: (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } },
                  set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private window */ } } };
  function current() {
    const q = new URLSearchParams(location.search).get("lang");
    const l = q || store.get("veda.lang") || document.documentElement.lang || "en";
    return l === "ms" || l === "bm" ? "ms" : "en";
  }
  function words(l) {
    document.querySelectorAll("[data-vf-en]").forEach((el) => { el.textContent = el.getAttribute("data-vf-" + l); });
    document.querySelectorAll(".vf-lang button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === l)));
  }
  window.vedaFrameLang = words;                      // the page calls this when it changes language itself
  words(current());
  // "Bigger text": the one saved text-size setting every page shares (localStorage "veda.big")
  const big = (on) => { document.documentElement.classList.toggle("big", on);
    document.querySelectorAll(".vf-big").forEach((b) => b.setAttribute("aria-pressed", String(on))); };
  big(store.get("veda.big") === "1");
  document.querySelectorAll(".vf-big").forEach((b) => b.addEventListener("click", () => {
    const on = !document.documentElement.classList.contains("big");
    store.set("veda.big", on ? "1" : "0");
    big(on);
  }));
  if (typeof window.vedaSetLang === "function") return;      // the page binds the buttons itself (index.html)
  document.querySelectorAll(".vf-lang button").forEach((b) => b.addEventListener("click", () => {
    const l = b.dataset.lang;
    store.set("veda.lang", l);
    words(l);
    const u = new URL(location.href);
    u.searchParams.set("lang", l);
    location.replace(u);
  }));
})();
