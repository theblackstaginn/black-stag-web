/* Black Stag Web Design | footer-only Runic Beacon, 2026-10-30.
   Symbolic maker's inscription. This does not affect marketing measurements. */
(() => {
  "use strict";
  function initRunicBeacon() {
    if (document.getElementById("bsw-beacon-modal")) return;
    const footers = document.querySelectorAll("footer.site-footer");
    if (!footers.length) return;

    const modal = document.createElement("div");
    modal.id = "bsw-beacon-modal";
    modal.className = "bsw-beacon-overlay";
    modal.hidden = true;
    modal.innerHTML = [
      '<div class="bsw-beacon-backdrop"></div>',
      '<section class="bsw-beacon-panel" role="dialog" aria-modal="true" aria-label="The Runic Beacon intention">',
      '<button class="bsw-beacon-close" type="button" aria-label="Close the Runic Beacon">×</button>',
      '<img class="bsw-beacon-art" src="/assets/runic-beacon-intention.webp" decoding="async" alt="An aged parchment inscribed with ᚠ ᚷ ᛃ and this intention: May those who seek what we create find their way here. May every exchange be fair and freely chosen. May our work bring abundance to maker and patron alike.">',
      '<p class="bsw-beacon-fallback" hidden>May those who seek what we create find their way here.<br>May every exchange be fair and freely chosen.<br>May our work bring abundance to maker and patron alike.</p>',
      '<div class="bsw-beacon-sparks" aria-hidden="true"></div>',
      '</section>'
    ].join("");
    document.body.append(modal);

    const closeButton = modal.querySelector(".bsw-beacon-close");
    const sparks = modal.querySelector(".bsw-beacon-sparks");
    const art = modal.querySelector(".bsw-beacon-art");
    const fallback = modal.querySelector(".bsw-beacon-fallback");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let active = false;
    let expiryTimer = 0;
    let fadeTimer = 0;
    let previousFocus = null;

    art.addEventListener("error", () => {
      art.hidden = true;
      fallback.hidden = false;
    });

    function clearTimers() {
      window.clearTimeout(expiryTimer);
      window.clearTimeout(fadeTimer);
      expiryTimer = fadeTimer = 0;
    }

    function finish() {
      clearTimers();
      active = false;
      modal.hidden = true;
      modal.classList.remove("bsw-beacon-vanishing");
      sparks.replaceChildren();
      document.removeEventListener("keydown", onKeyDown);
      if (previousFocus && previousFocus.isConnected) {
        previousFocus.focus({ preventScroll: true });
      }
      previousFocus = null;
    }

    function dissolve() {
      if (!active || modal.classList.contains("bsw-beacon-vanishing")) return;
      window.clearTimeout(expiryTimer);
      if (reducedMotion.matches) {
        finish();
        return;
      }
      modal.classList.add("bsw-beacon-vanishing");
      fadeTimer = window.setTimeout(finish, 1100);
    }

    function onKeyDown(event) {
      if (!active) return;
      if (event.key === "Escape") {
        event.preventDefault();
        dissolve();
      } else if (event.key === "Tab") {
        event.preventDefault();
        closeButton.focus();
      }
    }

    function reveal() {
      if (active) return;
      previousFocus = document.activeElement;
      active = true;
      modal.hidden = false;
      modal.classList.remove("bsw-beacon-vanishing");
      sparks.replaceChildren();
      if (!reducedMotion.matches) {
        for (let i = 0; i < 26; i++) {
          const particle = document.createElement("i");
          particle.style.setProperty("--x", String((i * 61 + 13) % 100) + "%");
          particle.style.setProperty("--y", String((i * 37 + 29) % 100) + "%");
          particle.style.setProperty("--delay", String((i % 9) * -0.23) + "s");
          sparks.append(particle);
        }
      }
      document.addEventListener("keydown", onKeyDown);
      closeButton.focus({ preventScroll: true });
      expiryTimer = window.setTimeout(dissolve, 10000);
    }

    for (const footer of footers) {
      if (footer.querySelector(".bsw-beacon-footer-mark")) continue;
      const mark = document.createElement("div");
      mark.className = "bsw-beacon-footer-mark";
      const button = document.createElement("button");
      button.className = "bsw-beacon-trigger";
      button.type = "button";
      button.textContent = "ᚠ ᚷ ᛃ";
      button.setAttribute("aria-label", "Reveal the Runic Beacon intention");
      button.title = "Discover the maker's intention";
      button.addEventListener("click", reveal);
      mark.append(button);
      footer.prepend(mark);
    }

    closeButton.addEventListener("click", dissolve);
    modal.querySelector(".bsw-beacon-backdrop").addEventListener("click", dissolve);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initRunicBeacon, { once: true });
  } else {
    initRunicBeacon();
  }
})();
