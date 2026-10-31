/* Black Stag Web Design | Footer Runic Beacon
   An opt-in maker's blessing, never an unsolicited marketing popup. */
(() => {
  "use strict";

  function initializeBeacon() {
    const footer = document.querySelector("footer.site-footer");
    if (!footer || document.getElementById("bsw-runic-beacon-trigger")) return;

    const host = footer.querySelector(":scope > .wrap") || footer;
    const holder = document.createElement("div");
    holder.className = "bsw-beacon-slot";
    holder.innerHTML =
      '<button type="button" class="bsw-beacon-trigger" id="bsw-runic-beacon-trigger" ' +
      'aria-label="Reveal the Runic Beacon intention" aria-haspopup="dialog" ' +
      'aria-controls="bsw-runic-beacon-dialog" title="A little secret in the smithy">' +
      '<span aria-hidden="true">ᚠ ᚷ ᛃ</span></button>';
    host.appendChild(holder);
    const trigger = holder.querySelector("button");

    const refreshToken = new URLSearchParams(window.location.search).get("_cb");
    const modal = document.createElement("div");
    modal.className = "bsw-beacon-modal";
    modal.id = "bsw-runic-beacon-dialog";
    modal.hidden = true;
    modal.innerHTML =
      '<div class="bsw-beacon-scrim"></div>' +
      '<section class="bsw-beacon-card" role="dialog" aria-modal="true" ' +
      'aria-label="A maker’s intention" aria-describedby="bsw-beacon-intention">' +
      '<button type="button" class="bsw-beacon-close" aria-label="Close the intention">×</button>' +
      '<img class="bsw-beacon-parchment" src="/assets/bswd-runic-beacon-digital-intention.webp" ' +
      'alt="Charcoal and copper digital plaque with three runes, fine circuit lines and a stag emblem, expressing honest craft, trust and prosperity for independent businesses.">' +
      '<p id="bsw-beacon-intention" class="bsw-beacon-visually-hidden">May those who value honest craft ' +
      'find their way here. May every partnership be built on trust and fair exchange. ' +
      'May our work help independent businesses prosper.</p>' +
      '<div class="bsw-beacon-fallback" hidden>' +
      '<p class="bsw-beacon-fallback-runes">ᚠ ᚷ ᛃ</p>' +
      '<p>May those who value honest craft find their way here.</p>' +
      '<p>May every partnership be built on trust and fair exchange.</p>' +
      '<p>May our work help independent businesses prosper.</p>' +
      '</div><div class="bsw-beacon-sparks" aria-hidden="true"></div>' +
      '</section>';
    document.body.appendChild(modal);
    if (refreshToken) {
      const artwork = modal.querySelector(".bsw-beacon-parchment");
      const artworkUrl = new URL(artwork.getAttribute("src"), window.location.origin);
      artworkUrl.searchParams.set("_cb", refreshToken);
      artwork.src = artworkUrl.href;
    }


    const scrim = modal.querySelector(".bsw-beacon-scrim");
    const card = modal.querySelector(".bsw-beacon-card");
    const close = modal.querySelector(".bsw-beacon-close");
    const sparks = modal.querySelector(".bsw-beacon-sparks");
    const image = modal.querySelector(".bsw-beacon-parchment");
    const fallback = modal.querySelector(".bsw-beacon-fallback");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let expiryTimer = null;
    let dissolveTimer = null;
    let previousFocus = null;
    let isOpen = false;
    let isClosing = false;

    function cancelTimers() {
      window.clearTimeout(expiryTimer);
      window.clearTimeout(dissolveTimer);
    }

    function hide() {
      cancelTimers();
      modal.hidden = true;
      modal.classList.remove("bsw-beacon-dissolving");
      sparks.replaceChildren();
      isOpen = false;
      isClosing = false;
      if (previousFocus && previousFocus.isConnected) {
        previousFocus.focus({ preventScroll: true });
      }
      previousFocus = null;
    }

    function dismiss() {
      if (!isOpen || isClosing) return;
      cancelTimers();
      if (reducedMotion.matches) {
        hide();
        return;
      }
      isClosing = true;
      modal.classList.add("bsw-beacon-dissolving");
      dissolveTimer = window.setTimeout(hide, 1100);
    }

    function reveal() {
      if (isOpen) hide();
      previousFocus = document.activeElement;
      isOpen = true;
      isClosing = false;
      modal.hidden = false;
      modal.classList.remove("bsw-beacon-dissolving");
      sparks.replaceChildren();
      if (!reducedMotion.matches) {
        for (let i = 0; i < 24; i++) {
          const ember = document.createElement("i");
          ember.style.setProperty("--bsw-x", ((i * 67 + 11) % 100) + "%");
          ember.style.setProperty("--bsw-y", ((i * 47 + 19) % 100) + "%");
          ember.style.setProperty("--bsw-n", String(i));
          sparks.appendChild(ember);
        }
      }
      close.focus({ preventScroll: true });
      expiryTimer = window.setTimeout(dismiss, 10000);
    }

    image.addEventListener("error", () => {
      image.hidden = true;
      fallback.hidden = false;
    });
    trigger.addEventListener("click", reveal);
    scrim.addEventListener("click", dismiss);
    close.addEventListener("click", dismiss);
    document.addEventListener("keydown", (event) => {
      if (!isOpen) return;
      if (event.key === "Escape") {
        event.preventDefault();
        dismiss();
      } else if (event.key === "Tab") {
        event.preventDefault();
        close.focus({ preventScroll: true });
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeBeacon, { once: true });
  } else {
    initializeBeacon();
  }
})();
