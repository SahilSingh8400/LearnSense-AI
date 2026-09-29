// LearnSense AI content script.
// Every attempt is stored locally for popup statistics.
// ONLY an Accepted submission is sent to the backend, and it contains the
// complete accepted code plus the attempt counters calculated locally.

(function () {
  "use strict";

  var SOURCE_PAGE = "lc-tracker-page";
  var SOURCE_CONTENT = "lc-tracker-content";

  var VERDICT_STRINGS = [
    "Accepted",
    "Wrong Answer",
    "Time Limit Exceeded",
    "Memory Limit Exceeded",
    "Runtime Error",
    "Output Limit Exceeded",
    "Compile Error",
    "Internal Error",
  ];

  var CORRECT_VERDICTS = { Accepted: true };
  var observer = null;
  var observerTimeout = null;
  var submissionInProgress = false;

  function injectPageScript() {
    if (document.getElementById("learnsense-page-inject")) return;
    var s = document.createElement("script");
    s.id = "learnsense-page-inject";
    s.src = chrome.runtime.getURL("page-inject.js");
    s.onload = function () {
      this.remove();
    };
    (document.head || document.documentElement).appendChild(s);
  }

  injectPageScript();

  function requestCode() {
    return new Promise(function (resolve) {
      var settled = false;
      var timeout = setTimeout(function () {
        if (settled) return;
        settled = true;
        window.removeEventListener("message", handler);
        resolve({ code: "", lang: "unknown" });
      }, 1800);

      function handler(event) {
        if (event.source !== window) return;
        var data = event.data;
        if (!data || data.source !== SOURCE_PAGE || data.type !== "CODE_VALUE")
          return;
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        window.removeEventListener("message", handler);
        resolve({ code: data.code || "", lang: data.lang || "unknown" });
      }

      window.addEventListener("message", handler);
      window.postMessage({ source: SOURCE_CONTENT, type: "GET_CODE" }, "*");
    });
  }

  function getProblemTitle() {
    var t = document.title || "";
    var idx = t.lastIndexOf(" - LeetCode");
    return idx > -1 ? t.slice(0, idx).trim() : t.trim() || "Untitled problem";
  }

  function getProblemSlug() {
    var match = window.location.pathname.match(/\/problems\/([^/]+)/);
    return match ? match[1] : "";
  }

  function getProblemUrl() {
    return window.location.href.split("?")[0];
  }

  function isSubmitButton(el) {
    if (!el || typeof el.closest !== "function") return false;
    if (el.closest('[data-e2e-locator="console-submit-button"]')) return true;
    var btn = el.closest("button");
    return !!(btn && btn.textContent && btn.textContent.trim() === "Submit");
  }

  function findVerdictInNode(node) {
    if (!node || node.nodeType !== 1) return null;
    var candidates = [node];
    if (typeof node.querySelectorAll === "function") {
      candidates = candidates.concat(
        Array.prototype.slice.call(node.querySelectorAll("*")),
      );
    }
    for (var i = 0; i < candidates.length; i++) {
      var el = candidates[i];
      var text = (el.textContent || "").trim();
      if (VERDICT_STRINGS.indexOf(text) !== -1 && el.children.length <= 2)
        return text;
    }
    return null;
  }

  function stopWatching() {
    if (observer) {
      observer.disconnect();
      observer = null;
    }
    if (observerTimeout) {
      clearTimeout(observerTimeout);
      observerTimeout = null;
    }
  }

  function watchForVerdict() {
    stopWatching();
    return new Promise(function (resolve) {
      var settled = false;
      observer = new MutationObserver(function (mutations) {
        for (var m = 0; m < mutations.length; m++) {
          var mutation = mutations[m];
          for (var n = 0; n < mutation.addedNodes.length; n++) {
            var verdict = findVerdictInNode(mutation.addedNodes[n]);
            if (verdict && !settled) {
              settled = true;
              stopWatching();
              resolve(verdict);
              return;
            }
          }
          if (mutation.type === "characterData") {
            var verdict2 = findVerdictInNode(mutation.target.parentElement);
            if (verdict2 && !settled) {
              settled = true;
              stopWatching();
              resolve(verdict2);
              return;
            }
          }
        }
      });

      observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
      });
      observerTimeout = setTimeout(function () {
        if (settled) return;
        settled = true;
        stopWatching();
        resolve(null);
      }, 25000);
    });
  }

  function getLocalData() {
    return new Promise(function (resolve) {
      chrome.storage.local.get(
        ["stats", "history", "problemStats"],
        function (data) {
          resolve({
            stats: data.stats || { correct: 0, wrong: 0 },
            history: data.history || [],
            problemStats: data.problemStats || {},
          });
        },
      );
    });
  }

  function setLocalData(values) {
    return new Promise(function (resolve) {
      chrome.storage.local.set(values, resolve);
    });
  }

  async function saveSubmission(verdict, code, lang) {
    var data = await getLocalData();
    var stats = data.stats;
    var history = data.history;
    var problemStats = data.problemStats;
    var problemKey = getProblemSlug() || getProblemUrl() || getProblemTitle();

    if (CORRECT_VERDICTS[verdict]) stats.correct += 1;
    else stats.wrong += 1;

    if (!problemStats[problemKey]) {
      problemStats[problemKey] = {
        title: getProblemTitle(),
        slug: getProblemSlug(),
        url: getProblemUrl(),
        correct: 0,
        wrong: 0,
      };
    }

    if (verdict === "Accepted") problemStats[problemKey].correct += 1;
    else problemStats[problemKey].wrong += 1;

    var entry = {
      title: getProblemTitle(),
      problemSlug: getProblemSlug(),
      problemUrl: getProblemUrl(),
      verdict: verdict,
      code: code || "",
      lang: lang || "unknown",
      timestamp: Date.now(),
    };

    entry.rightAttempts = problemStats[problemKey].correct;
    entry.wrongAttempts = problemStats[problemKey].wrong;
    entry.totalAttempts = entry.rightAttempts + entry.wrongAttempts;

    history.unshift(entry);
    if (history.length > 200) history.length = 200;

    await setLocalData({
      stats: stats,
      history: history,
      problemStats: problemStats,
    });

    if (verdict === "Accepted") {
      chrome.runtime.sendMessage(
        { action: "syncAccepted", entry: entry },
        function (result) {
          if (chrome.runtime.lastError) {
            console.warn(
              "[LearnSense] Backend sync unavailable:",
              chrome.runtime.lastError.message,
            );
            return;
          }
          console.log("[LearnSense] Accepted submission sync:", result);
        },
      );
    }
  }

  function handleSubmitClick() {
    if (submissionInProgress) return;
    submissionInProgress = true;

    var verdictPromise = watchForVerdict();
    requestCode()
      .then(function (codeResult) {
        return verdictPromise.then(function (verdict) {
          if (verdict) {
            return saveSubmission(verdict, codeResult.code, codeResult.lang);
          }
        });
      })
      .catch(function (error) {
        console.error("[LearnSense] Save failed:", error);
      })
      .finally(function () {
        setTimeout(function () {
          submissionInProgress = false;
        }, 800);
      });
  }

  document.addEventListener(
    "click",
    function (e) {
      if (isSubmitButton(e.target)) handleSubmitClick();
    },
    true,
  );
})();
