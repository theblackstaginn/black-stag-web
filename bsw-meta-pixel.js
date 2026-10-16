/* Black Stag Web Design | Meta Pixel
 * Canonical dataset: Black Stag Web Design Website (2289161921865343).
 * Sitewide PageView only. The Website Checkup page separately tracks Lead
 * after successful submission; do not pass names, emails, or form fields.
 */
(() => {
  "use strict";

  // Prevent duplicate initialization if this script is loaded twice.
  if (window.__blackStagMetaPageViewSent) return;
  window.__blackStagMetaPageViewSent = true;

  !function(f,b,e,v,n,t,s) {
    if (f.fbq) return;
    n = f.fbq = function() {
      n.callMethod ? n.callMethod.apply(n,arguments) : n.queue.push(arguments);
    };
    if (!f._fbq) f._fbq = n;
    n.push = n;
    n.loaded = true;
    n.version = "2.0";
    n.queue = [];
    t = b.createElement(e);
    t.async = true;
    t.src = v;
    s = b.getElementsByTagName(e)[0];
    s.parentNode.insertBefore(t,s);
  }(window, document, "script", "https://connect.facebook.net/en_US/fbevents.js");

  window.fbq("init", "2289161921865343");
  window.fbq("track", "PageView");
})();
