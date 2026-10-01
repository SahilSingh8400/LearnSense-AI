// Runs in the page context so editor APIs and DOM state are available.
(function () {
  "use strict";
  var SOURCE_PAGE = "lc-tracker-page";
  var SOURCE_CONTENT = "lc-tracker-content";

  function languageFromPage() {
    var select = document.querySelector(
      "select[name*='language' i], select[id*='language' i], [data-testid*='language' i]"
    );
    return select ? (select.value || select.textContent || "").trim() : "";
  }

  function getEditorCode() {
    try {
      if (window.monaco && window.monaco.editor) {
        var models = window.monaco.editor.getModels();
        if (models && models.length) {
          var model = models[0];
          for (var modelIndex = 1; modelIndex < models.length; modelIndex++) {
            if (models[modelIndex].getValue().length > model.getValue().length) {
              model = models[modelIndex];
            }
          }
          return {
            code: model.getValue(),
            lang: typeof model.getLanguageId === "function" ? model.getLanguageId() : languageFromPage(),
          };
        }
      }
    } catch (error) {
      console.warn("[LearnSense] Monaco code extraction failed:", error);
    }

    var codeMirrorContainer = document.querySelector(".CodeMirror");
    if (codeMirrorContainer && codeMirrorContainer.CodeMirror &&
        typeof codeMirrorContainer.CodeMirror.getValue === "function") {
      return {
        code: codeMirrorContainer.CodeMirror.getValue(),
        lang: languageFromPage(),
      };
    }

    var codeMirror = document.querySelector(".CodeMirror textarea, textarea[data-testid*='code' i]");
    if (codeMirror && typeof codeMirror.value === "string") {
      return { code: codeMirror.value, lang: languageFromPage() };
    }

    var textareas = document.querySelectorAll("textarea");
    for (var textareaIndex = 0; textareaIndex < textareas.length; textareaIndex++) {
      if (textareas[textareaIndex].value) {
        return { code: textareas[textareaIndex].value, lang: languageFromPage() };
      }
    }

    try {
      if (window.ace && typeof window.ace.edit === "function") {
        var aceEditors = document.querySelectorAll(".ace_editor");
        for (var editorIndex = 0; editorIndex < aceEditors.length; editorIndex++) {
          var aceEditor = window.ace.edit(aceEditors[editorIndex]);
          var aceCode = aceEditor.getValue();
          if (aceCode) return { code: aceCode, lang: languageFromPage() };
        }
      }
    } catch (aceError) {
      console.warn("[LearnSense] Ace code extraction failed:", aceError);
    }

    var cm6 = document.querySelector(".cm-editor");
    if (cm6) {
      var cmView = cm6.cmView || cm6.view || cm6.editorView;
      if (cmView && cmView.state && cmView.state.doc) {
        return { code: cmView.state.doc.toString(), lang: languageFromPage() };
      }
    }

    var aceLines = document.querySelectorAll(".ace_text-layer .ace_line");
    if (aceLines.length) {
      return {
        code: Array.prototype.map.call(aceLines, function (line) { return line.textContent; }).join("\n"),
        lang: languageFromPage(),
      };
    }

    var editable = document.querySelector("[contenteditable='true']");
    if (editable) return { code: editable.innerText || editable.textContent || "", lang: languageFromPage() };
    return { code: "", lang: languageFromPage() };
  }

  window.addEventListener("message", function (event) {
    if (event.source !== window || !event.data ||
        event.data.source !== SOURCE_CONTENT || event.data.type !== "GET_CODE") return;
    var result = getEditorCode();
    window.postMessage({
      source: SOURCE_PAGE, type: "CODE_VALUE", code: result.code, lang: result.lang,
    }, "*");
  });
})();
