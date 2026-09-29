// LearnSense API base URL — auto-detected for production, localhost for development.
// If deployed on Render, the dashboard and API share the same domain or you can
// override by setting this manually to your Render backend URL.
(function () {
  var host = window.location.hostname;
  if (host === 'localhost' || host === '127.0.0.1') {
    // Local development
    window.LEARNSENSE_API_BASE = 'http://localhost:5000/api';
  } else {
    // Production — API is served from the backend, not the static site.
    // *** CHANGE THIS to your Render backend URL ***
    window.LEARNSENSE_API_BASE = 'https://learnsense-ai.onrender.com/api';
  }
})();
