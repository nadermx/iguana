/* Iguana Comedy site script: ticket checkout widgets + pageview tracking. Drop-in for Kintana's /_t/k.js. */
(function () {
  if (window.__iguanaK) return;
  window.__iguanaK = 1;
  var S = document.currentScript;
  var A = (S && S.getAttribute("data-api-base")) || "{{ backend_url }}";
  var T = (S && S.getAttribute("data-token")) || "";
  A = A.replace(/\/$/, "");

  function vid() {
    try {
      var v = localStorage.getItem("kintana_page_vid");
      if (!v) {
        v = Math.random().toString(36).slice(2) + Date.now().toString(36);
        localStorage.setItem("kintana_page_vid", v);
      }
      return v;
    } catch (e) {
      return "";
    }
  }
  var V = vid();

  function post(path, body) {
    try {
      var data = JSON.stringify(body);
      if (navigator.sendBeacon) {
        navigator.sendBeacon(A + path, new Blob([data], { type: "text/plain" }));
      } else {
        fetch(A + path, { method: "POST", body: data, keepalive: true, mode: "cors", credentials: "omit" });
      }
    } catch (e) {}
  }

  function cookie(name) {
    try {
      var hit = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
      return hit ? decodeURIComponent(hit[2]) : "";
    } catch (e) {
      return "";
    }
  }

  function utm() {
    var out = {};
    try {
      var params = new URLSearchParams(location.search);
      params.forEach(function (v, k) {
        if (k.indexOf("utm_") === 0 || k === "fbclid" || k === "gclid" || k === "ttclid" || k === "ref") out[k.replace("utm_", "")] = v;
      });
      // `ref` names our own links (share, after-show, om-thanks, om-email), so /stats/ can say which one sold.
      // Meta matches a server-side sale on these. The checkout iframe is on another origin and cannot read them,
      // so they are collected here and posted with the order; see backend/sales/ad_reporting.py.
      out.fbp = cookie("_fbp");
      // The pixel normally writes _fbc from fbclid, but it is the first thing an ad blocker stops. Rebuilding it
      // in Meta's own format keeps the click attributable when the pixel never ran.
      out.fbc = cookie("_fbc") || (params.get("fbclid") ? "fb.1." + Date.now() + "." + params.get("fbclid") : "");
      // TikTok's equivalents: the browser id its pixel writes on this origin. ttclid itself is collected above.
      out.ttp = cookie("_ttp");
      // The page the fan actually saw, rather than the iframe URL, so Meta reports results per landing page.
      out.pageUrl = location.href.slice(0, 200);
    } catch (e) {}
    for (var key in out) {
      if (out[key] === "") delete out[key];
    }
    return out;
  }

  function fanToken() {
    try {
      return (localStorage.getItem("kintana_access_token") || localStorage.getItem("kintana_fan_access_token") || "").trim();
    } catch (e) {
      return "";
    }
  }

  function track(name, props) {
    post("/api/ingest/event", { token: T, visitorKey: V, name: String(name || ""), props: props || null });
  }

  function bootWidgets() {
    window.addEventListener("message", function (e) {
      var d = e.data;
      if (!d || e.origin !== A) return;
      if (d.type === "kintana-embed-checkout-success" && typeof d.url === "string") {
        track("Purchase", { url: d.url });
        window.location.assign(d.url);
      }
      if (d.type === "kintana-fan-auth-request" && e.source) {
        e.source.postMessage({ type: "kintana-fan-auth", token: fanToken(), attribution: utm() }, A);
      }
    });

    document.querySelectorAll("[data-kintana-widget]").forEach(function (el) {
      var raw = el.getAttribute("data-kintana-widget") || "";
      var id = raw.indexOf("event:") === 0 ? raw.slice(6) : "";
      if (!id || el.querySelector("iframe")) return;
      var iframe = document.createElement("iframe");
      // The page language rides along so the checkout, order page and email match the site the fan is on.
      var lang = el.getAttribute("data-kintana-locale") || document.documentElement.lang || "en";
      // A host page that prints the demand line itself turns the iframe's copy off, so it is not said twice.
      var demand = el.getAttribute("data-kintana-demand") === "off" ? "&demand=0" : "";
      iframe.src = A + "/embed/event/" + encodeURIComponent(id) + "?embedded=1&lang=" + encodeURIComponent(lang) + demand;
      iframe.title = el.getAttribute("aria-label") || "Ticket checkout";
      iframe.setAttribute("allow", "payment *");
      // The frame is always sized to its content once settled, so its own scrollbar could only ever flash.
      iframe.setAttribute("scrolling", "no");
      // Take the height the host page has already painted. It reserves the space in CSS, per breakpoint,
      // because the checkout wraps to the width it is given and a card form is three times the height of a
      // name-and-email one. Reading it back means the iframe is inserted at exactly the size of the hole it
      // fills, so the swap itself can never move the page. data-kintana-height still overrides it.
      var box = el.getBoundingClientRect().height;
      var cs = window.getComputedStyle(el);
      var pad = (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0) +
                (parseFloat(cs.borderTopWidth) || 0) + (parseFloat(cs.borderBottomWidth) || 0);
      var reserved = parseInt(el.getAttribute("data-kintana-height") || "", 10) ||
                     Math.max(160, Math.round(box - pad)) || 460;
      iframe.style.cssText = "width:100%;border:0;display:block;background:transparent;height:" + reserved + "px";
      el.innerHTML = "";
      el.appendChild(iframe);
      // The reserve is held exactly while the form is still arriving, neither floor nor ceiling to follow. What
      // Stripe draws is not knowable from here: a wallet row appears only on a device that has a wallet, and
      // Link only for an email it recognises. So the space is held until the checkout says it has settled,
      // and then the box fits its contents exactly. Holding the floor after that would leave white space
      // above the Pay button on any browser that drew a shorter form, which looks broken in a way a brief
      // movement does not.
      var settled = false, lastHeight = 0;
      // The floor is only ever a loan. If the checkout never reports that it has settled, because its script
      // died or Stripe never finished drawing, the reserved space would otherwise be held open forever around
      // a short form. Give it ten seconds, then fit whatever the iframe last reported.
      setTimeout(function () {
        settled = true;
        if (lastHeight) iframe.style.height = lastHeight + "px";
      }, 10000);
      window.addEventListener("message", function (e) {
        var d = e.data;
        if (d && d.type === "kintana-embed-height" && typeof d.height === "number" && e.source === iframe.contentWindow) {
          var h = Math.max(160, d.height | 0);
          lastHeight = h;
          // Settled means the CHECKOUT says so, never "it got taller than the reserve". Stripe overshoots by
          // about 100px for a moment while it draws, and treating that as final made the box grow and shrink
          // back; on an event page the hero photo is cropped to the section the box sits in, so it visibly
          // zoomed in and out (owner, 2026-10-09). Until then the reserve is held exactly, and the overshoot
          // stays inside the frame for the second it lasts.
          if (d.settled) settled = true;
          iframe.style.height = (settled ? h : reserved) + "px";
        }
      });
      iframe.addEventListener("load", function () {
        iframe.contentWindow.postMessage({ type: "kintana-fan-auth", token: fanToken(), attribution: utm() }, A);
      });
    });
  }

  function pageview() {
    var detail = { url: location.href, referrer: document.referrer || "", utm: utm() };
    try {
      window.dispatchEvent(new CustomEvent("kintana:pageview", { detail: detail }));
    } catch (e) {}
    post("/api/ingest/pageview", { token: T, visitorKey: V, url: detail.url, referrer: detail.referrer, utm: detail.utm });
  }

  window.Kintana = window.Kintana || { track: track, page: track, identify: function () {}, consent: function () {} };

  function boot() {
    bootWidgets();
    pageview();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
