// LearnSense API base URL — local / offline first.
(function () {
  var host = window.location.hostname;
  var port = window.location.port;
  if (host === 'localhost' || host === '127.0.0.1' || host === '') {
    // Local development / direct file or local server
    if (port === '5000') {
      window.LEARNSENSE_API_BASE = window.location.origin + '/api';
    } else {
      window.LEARNSENSE_API_BASE = 'http://localhost:5000/api';
    }
  } else {
    // If hosted on custom local IP or LAN
    window.LEARNSENSE_API_BASE = window.location.origin + '/api';
  }
})();
