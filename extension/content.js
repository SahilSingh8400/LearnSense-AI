// LearnSense AI content script.
// The site adapter keeps submission tracking consistent across supported
// coding platforms while retaining the existing local-storage format.

(function () {
  "use strict";

  var SOURCE_PAGE = "lc-tracker-page";
  var SOURCE_CONTENT = "lc-tracker-content";
  var observer = null;
  var observerTimeout = null;
  var submissionInProgress = false;

  var PLATFORM_CONFIG = {
    leetcode: {
      name: "LeetCode",
      titleSuffix: " - LeetCode",
      slugPattern: /\/problems\/([^/]+)/,
      submit: function (text) { return text === "submit"; },
    },
    codechef: {
      name: "CodeChef",
      slugPattern: /\/(?:problems|practice|start|contests)\/([^/?#]+)/,
      submit: function (text) {
        return text.indexOf("submit") !== -1 && text.indexOf("run") === -1;
      },
    },
    hackerrank: {
      name: "HackerRank",
      slugPattern: /\/challenges\/([^/?#]+)/,
      submit: function (text) { return text.indexOf("submit") !== -1; },
    },
  };

  var VERDICT_PATTERNS = [
    { verdict: "Accepted", patterns: ["accepted", "success", "ac", "all test cases passed", "congratulations!"] },
    { verdict: "Wrong Answer", patterns: ["wrong answer", "test case failed", "failed test case", "wa", "partially accepted"] },
    { verdict: "Time Limit Exceeded", patterns: ["time limit exceeded", "time limit", "tle"] },
    { verdict: "Memory Limit Exceeded", patterns: ["memory limit exceeded", "memory limit", "mle"] },
    { verdict: "Runtime Error", patterns: ["runtime error", "runtime exception", "re"] },
    { verdict: "Output Limit Exceeded", patterns: ["output limit exceeded", "ole"] },
    { verdict: "Compile Error", patterns: ["compile error", "compilation error", "ce"] },
    { verdict: "Internal Error", patterns: ["internal error", "system error"] },
  ];

  function getPlatform() {
    var host = window.location.hostname.toLowerCase();
    if (host === "leetcode.com" || host.endsWith(".leetcode.com")) return "leetcode";
    if (host === "codechef.com" || host.endsWith(".codechef.com")) return "codechef";
    if (host === "hackerrank.com" || host.endsWith(".hackerrank.com")) return "hackerrank";
    return null;
  }

  var platform = getPlatform();
  if (!platform) return;

  function injectPageScript() {
    if (document.getElementById("learnsense-page-inject")) return;
    var script = document.createElement("script");
    script.id = "learnsense-page-inject";
    script.src = chrome.runtime.getURL("page-inject.js");
    script.onload = function () { this.remove(); };
    (document.head || document.documentElement).appendChild(script);
  }

  injectPageScript();

  function getDomCode() {
    var codeMirrorContainer = document.querySelector(".CodeMirror");
    if (codeMirrorContainer && codeMirrorContainer.CodeMirror &&
        typeof codeMirrorContainer.CodeMirror.getValue === "function") {
      return { code: codeMirrorContainer.CodeMirror.getValue(), lang: "unknown" };
    }
    var textarea = document.querySelector(
      ".CodeMirror textarea, textarea[data-testid*='code' i], textarea[aria-label*='code' i]"
    );
    if (textarea && textarea.value) return { code: textarea.value, lang: "unknown" };
    var textareas = document.querySelectorAll("textarea");
    for (var textareaIndex = 0; textareaIndex < textareas.length; textareaIndex++) {
      if (textareas[textareaIndex].value) {
        return { code: textareas[textareaIndex].value, lang: "unknown" };
      }
    }
    var aceLines = document.querySelectorAll(".ace_text-layer .ace_line");
    if (aceLines.length) {
      return {
        code: Array.prototype.map.call(aceLines, function (line) { return line.textContent; }).join("\n"),
        lang: "unknown",
      };
    }
    var editable = document.querySelector("[contenteditable='true']");
    if (editable && (editable.innerText || editable.textContent)) {
      return { code: editable.innerText || editable.textContent, lang: "unknown" };
    }
    return null;
  }

  function requestCode() {
    return new Promise(function (resolve) {
      var settled = false;
      var attempts = 0;
      var retryTimer = null;
      var timeout = setTimeout(function () {
        if (settled) return;
        settled = true;
        if (retryTimer) clearInterval(retryTimer);
        window.removeEventListener("message", handler);
        resolve(getDomCode() || { code: "", lang: "unknown" });
      }, 5000);

      function handler(event) {
        if (event.source !== window || !event.data ||
            event.data.source !== SOURCE_PAGE || event.data.type !== "CODE_VALUE" ||
            settled) return;
        var fallback = getDomCode() || {};
        var code = event.data.code || fallback.code || "";
        if (!code && attempts < 10) return;
        settled = true;
        clearTimeout(timeout);
        if (retryTimer) clearInterval(retryTimer);
        window.removeEventListener("message", handler);
        resolve({ code: code, lang: event.data.lang || fallback.lang || "unknown" });
      }

      window.addEventListener("message", handler);
      window.postMessage({ source: SOURCE_CONTENT, type: "GET_CODE" }, "*");
      retryTimer = setInterval(function () {
        attempts += 1;
        window.postMessage({ source: SOURCE_CONTENT, type: "GET_CODE" }, "*");
      }, 400);
    });
  }

  function getProblemTitle() {
    var config = PLATFORM_CONFIG[platform];
    var title = document.querySelector('meta[property="og:title"]');
    var heading = document.querySelector("h1");
    var value = (title && title.content) || (heading && heading.textContent) || document.title || "";
    if (config.titleSuffix && value.lastIndexOf(config.titleSuffix) !== -1) {
      value = value.slice(0, value.lastIndexOf(config.titleSuffix));
    }
    return value.replace(/\s+/g, " ").trim() || "Untitled problem";
  }

  function getProblemSlug() {
    var match = window.location.pathname.match(PLATFORM_CONFIG[platform].slugPattern);
    if (match) return decodeURIComponent(match[1]).replace(/\/$/, "");
    var parts = window.location.pathname.split("/").filter(Boolean);
    return parts.length ? parts[parts.length - 1] : "";
  }

  function getProblemUrl() {
    return window.location.href.split("?")[0].split("#")[0];
  }

  function isSubmitButton(element) {
    if (!element || typeof element.closest !== "function") return false;
    var button = element.closest(
      "button, [role='button'], input[type='submit'], [class*='submit' i]"
    );
    if (!button) return false;
    var text = (button.textContent || button.value || "").replace(/\s+/g, " ").trim().toLowerCase();
    var label = (button.getAttribute("aria-label") || button.getAttribute("title") || "").trim().toLowerCase();
    if (PLATFORM_CONFIG[platform].submit(text) || PLATFORM_CONFIG[platform].submit(label)) {
      return true;
    }
    if (platform !== "codechef") return false;
    var ancestor = button.parentElement;
    for (var depth = 0; ancestor && depth < 3; depth++, ancestor = ancestor.parentElement) {
      var ancestorText = (ancestor.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
      var ancestorClass = (ancestor.className || "").toString().toLowerCase();
      if (ancestorClass.indexOf("submit") !== -1 &&
          ancestorText.indexOf("submit") !== -1) {
        return true;
      }
    }
    return false;
  }

  function normalizeVerdict(text) {
    var value = (text || "").replace(/\s+/g, " ").trim().toLowerCase();
    for (var i = 0; i < VERDICT_PATTERNS.length; i++) {
      for (var j = 0; j < VERDICT_PATTERNS[i].patterns.length; j++) {
        var pattern = VERDICT_PATTERNS[i].patterns[j];
        var isAccepted = VERDICT_PATTERNS[i].verdict === "Accepted";
        var shortCode = ["ac", "wa", "tle", "mle", "re", "ole", "ce"].indexOf(pattern) !== -1;
        var exactAcceptedLabel = isAccepted &&
          (pattern === "accepted" || pattern === "success" || shortCode);
        if (value === pattern || (!isAccepted && value.indexOf(pattern) !== -1) ||
            (exactAcceptedLabel && value === pattern) ||
            (isAccepted && !exactAcceptedLabel && value.indexOf(pattern) !== -1) ||
            (shortCode && new RegExp("(^|\\s|[-:])" + pattern + "($|\\s|[-:])").test(value))) {
          return VERDICT_PATTERNS[i].verdict;
        }
      }
    }
    return null;
  }

  function findVerdictInNode(node) {
    if (!node || node.nodeType !== 1) return null;
    var candidates = [node];
    if (node.querySelectorAll) {
      candidates = candidates.concat(Array.prototype.slice.call(node.querySelectorAll("*")));
    }
    for (var i = 0; i < candidates.length; i++) {
      var verdict = normalizeVerdict(candidates[i].textContent || "");
      if (verdict && candidates[i].children.length <= 2) return verdict;
    }
    return null;
  }

  function stopWatching() {
    if (observer) observer.disconnect();
    observer = null;
    if (observerTimeout) clearTimeout(observerTimeout);
    observerTimeout = null;
  }

  function watchForVerdict() {
    stopWatching();
    return new Promise(function (resolve) {
      var settled = false;
      function finish(verdict) {
        if (settled) return;
        settled = true;
        stopWatching();
        resolve(verdict);
      }
      observer = new MutationObserver(function (mutations) {
        for (var i = 0; i < mutations.length; i++) {
          for (var j = 0; j < mutations[i].addedNodes.length; j++) {
            var verdict = findVerdictInNode(mutations[i].addedNodes[j]);
            if (verdict) return finish(verdict);
          }
          if (mutations[i].type === "characterData") {
            var changed = mutations[i].target.parentElement;
            var changedVerdict = findVerdictInNode(changed);
            if (changedVerdict) return finish(changedVerdict);
          }
        }
      });
      observer.observe(document.body, { childList: true, subtree: true, characterData: true });
      observerTimeout = setTimeout(function () {
        finish(null);
      }, 30000);
    });
  }

  function getLocalData() {
    return new Promise(function (resolve) {
      chrome.storage.local.get(["stats", "history", "problemStats"], function (data) {
        resolve({
          stats: data.stats || { correct: 0, wrong: 0 },
          history: data.history || [],
          problemStats: data.problemStats || {},
        });
      });
    });
  }

  function setLocalData(values) {
    return new Promise(function (resolve) { chrome.storage.local.set(values, resolve); });
  }

  async function saveSubmission(verdict, code, lang) {
    var data = await getLocalData();
    var problemKey = platform + ":" + (getProblemSlug() || getProblemUrl() || getProblemTitle());
    if (verdict === "Accepted") data.stats.correct += 1;
    else data.stats.wrong += 1;
    if (!data.problemStats[problemKey]) {
      data.problemStats[problemKey] = {
        title: getProblemTitle(), slug: getProblemSlug(), url: getProblemUrl(),
        platform: platform, correct: 0, wrong: 0,
      };
    }
    if (verdict === "Accepted") data.problemStats[problemKey].correct += 1;
    else data.problemStats[problemKey].wrong += 1;

    var entry = {
      platform: platform,
      title: getProblemTitle(),
      problemSlug: getProblemSlug(),
      problemUrl: getProblemUrl(),
      verdict: verdict,
      code: code || "",
      lang: lang || "unknown",
      timestamp: Date.now(),
    };
    entry.rightAttempts = data.problemStats[problemKey].correct;
    entry.wrongAttempts = data.problemStats[problemKey].wrong;
    entry.totalAttempts = entry.rightAttempts + entry.wrongAttempts;
    data.history.unshift(entry);
    if (data.history.length > 200) data.history.length = 200;
    await setLocalData({ stats: data.stats, history: data.history, problemStats: data.problemStats });
    if (verdict === "Accepted") {
      chrome.runtime.sendMessage({ action: "syncAccepted", entry: entry });
    }
  }

  function handleSubmitClick() {
    if (submissionInProgress) return;
    submissionInProgress = true;
    var verdictPromise = watchForVerdict();
    requestCode().then(function (codeResult) {
      return verdictPromise.then(function (verdict) {
        if (verdict) return saveSubmission(verdict, codeResult.code, codeResult.lang);
      });
    }).catch(function (error) {
      console.error("[LearnSense] Save failed:", error);
    }).finally(function () {
      setTimeout(function () { submissionInProgress = false; }, 800);
    });
  }

  document.addEventListener("click", function (event) {
    if (isSubmitButton(event.target)) handleSubmitClick();
  }, true);
})();
