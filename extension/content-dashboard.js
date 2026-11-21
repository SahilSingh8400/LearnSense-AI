// LearnSense AI - Dashboard SSO Bridge
// Synchronizes authentication between Web Dashboard and Chrome Extension
(function () {
  "use strict";

  function syncAuthToExtension() {
    try {
      var token = localStorage.getItem("learnsense_access_token");
      var refreshToken = localStorage.getItem("learnsense_refresh_token") || "";
      if (token && chrome && chrome.runtime && chrome.runtime.sendMessage) {
        chrome.runtime.sendMessage({
          action: "saveAuth",
          token: token,
          refreshToken: refreshToken,
        });
      }
    } catch (e) {
      // Storage access or extension context invalidated
    }
  }

  // Sync on page load if logged in
  syncAuthToExtension();

  // Listen for storage events (e.g. login/logout in dashboard)
  window.addEventListener("storage", function (e) {
    if (e.key === "learnsense_access_token" && e.newValue) {
      syncAuthToExtension();
    }
  });

  // Listen for custom dispatch from dashboard app.js
  window.addEventListener("message", function (event) {
    if (event.source !== window || !event.data) return;
    if (event.data.type === "LEARNSENSE_DASHBOARD_AUTH") {
      syncAuthToExtension();
    }
  });
})();
