/* BenchWeave generic host script (bw-host.js).
 *
 * The one host-side script every BenchWeave host page loads. Generic by
 * contract: it drives behaviour from data-* attributes the page templates
 * emit, never from host-specific selectors. Responsibilities (G2 design
 * record §2.6):
 *
 *   - htmx bootstrap: the htmx config rides the page's
 *     <meta name="htmx-config"> element (allowEval=false,
 *     selfRequestsOnly=true — the CSP posture); this script never
 *     overrides it, only reads documented values.
 *   - CSRF token delivery (G3a FOLD-1): the shell renders the session's
 *     token as <meta name="bw-csrf-token">; an htmx:configRequest
 *     listener stamps it onto every htmx request (x-csrf-token), so a
 *     session-bearing POST passes the gateway's CsrfGuard without any
 *     inline handler. A page without the meta — a session-less view —
 *     sends no header, and the guard's cookie-less branch applies.
 *   - SSE connect: an element carrying data-bw-stream-url opens one
 *     EventSource; data-bw-stream-target names the swap target for event
 *     payloads. The connection is read-only: it never issues writes.
 *   - per-frame swap coalescing: events landing between animation frames
 *     are queued and flushed together (one DOM mutation boundary per
 *     frame), so a burst does not thrash the page.
 *   - live-region announcements: a "bw-announce" DOM event (or a direct
 *     bw.announce(text) call) writes textContent into the element carrying
 *     data-bw-announce — the ARIA live region. State changes announce;
 *     sample values never do (that is the templates' contract).
 *   - theme handling: the root element's data-theme follows the
 *     prefers-color-scheme media query (no manual override in G2).
 *
 * No eval, no remote fetches, no inline handlers: script-src 'self' with
 * connect-src 'self' must hold with this file as shipped.
 */
(function () {
  "use strict";

  var root = document.documentElement;

  /* --- theme (prefers-color-scheme only; no manual override in G2) --- */

  function applyTheme(media) {
    root.setAttribute("data-theme", media.matches ? "dark" : "light");
  }

  var themeQuery = window.matchMedia("(prefers-color-scheme: dark)");
  applyTheme(themeQuery);
  themeQuery.addEventListener("change", applyTheme);

  /* --- live-region announcements (data-bw-announce) --- */

  function announceRegion() {
    return document.querySelector("[data-bw-announce]");
  }

  function announce(text) {
    var region = announceRegion();
    if (!region) {
      return;
    }
    // textContent, never innerHTML: announcements are data, not markup.
    region.textContent = text;
  }

  document.addEventListener("bw-announce", function (event) {
    if (event && typeof event.detail === "string") {
      announce(event.detail);
    }
  });

  /* --- per-frame swap coalescing --- */

  var pendingSwaps = [];
  var flushScheduled = false;

  function flushSwaps() {
    flushScheduled = false;
    var batch = pendingSwaps;
    pendingSwaps = [];
    for (var i = 0; i < batch.length; i += 1) {
      var item = batch[i];
      var target = item.target;
      if (!target || !target.parentNode) {
        continue; // the frame went away between queue and flush
      }
      // Swapping via range-adjacent nodes keeps one mutation per frame
      // boundary; htmx (when present) owns its own swaps elsewhere.
      // PROVENANCE INVARIANT: the only html entering this swap is a
      // server-templated fragment pushed over the SSE connection — this
      // script constructs no content of its own and fetches nothing (no
      // fetch, no XHR); everything rendered originated server-side.
      var holder = document.createElement("template");
      holder.innerHTML = item.html;
      target.replaceChildren(holder.content);
    }
  }

  function queueSwap(target, html) {
    pendingSwaps.push({ target: target, html: html });
    if (!flushScheduled) {
      flushScheduled = true;
      window.requestAnimationFrame(flushSwaps);
    }
  }

  /* --- SSE connect (data-bw-stream-url, read-only) --- */

  function connectStreams() {
    var sources = document.querySelectorAll("[data-bw-stream-url]");
    for (var i = 0; i < sources.length; i += 1) {
      var element = sources[i];
      if (element.dataset.bwConnected === "true") {
        continue; // one connection per element, idempotent on re-run
      }
      element.dataset.bwConnected = "true";
      var targetSelector = element.getAttribute("data-bw-stream-target");
      var source = new EventSource(element.getAttribute("data-bw-stream-url"));
      source.onmessage = function (event) {
        var target = targetSelector
          ? document.querySelector(targetSelector)
          : element;
        if (target) {
          queueSwap(target, event.data);
        }
      };
      // Gap events carry watermarks, not content: announce, never swap.
      source.addEventListener("bw-gap", function (event) {
        announce(
          "Event stream had a gap" +
            (event.data ? ": " + event.data : "") +
            ". Re-reading the affected views."
        );
      });
      // Stream termination (bw-end): announce through the same ARIA
      // channel — without this the browser's stream stops silently.
      source.addEventListener("bw-end", function (event) {
        announce(
          "Event stream ended" + (event.data ? ": " + event.data : "") + "."
        );
      });
    }
  }

  function boot() {
    connectStreams();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  /* --- CSRF token delivery (G3a FOLD-1) --- */

  // The CsrfGuard refuses every session-bearing state change without the
  // page-delivered token (NFR-S4). The token rides the <meta
  // name="bw-csrf-token"> element the shell renders; this listener stamps
  // it onto EVERY htmx request, so the control forms carry it without any
  // inline handler (none exist: the CSP forbids them). A page without the
  // meta — a session-less view — sends no header, and the guard's
  // cookie-less branch applies.
  document.addEventListener("htmx:configRequest", function (event) {
    var meta = document.querySelector('meta[name="bw-csrf-token"]');
    if (meta && event.detail && event.detail.headers) {
      event.detail.headers["x-csrf-token"] = meta.content || "";
    }
  });

  /* Host-exposed surface: the announce hook pages may call directly. */
  window.bw = { announce: announce };
})();
