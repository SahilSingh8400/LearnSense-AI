// page-inject.js
//
// This file is loaded with a <script src="..."> tag by content.js, which
// means it runs in the PAGE's own JavaScript context (the "main world"),
// not the isolated content-script sandbox. That's the only place
// `window.monaco` (LeetCode's code editor instance) actually exists, so
// it's the only place we can reliably pull the full, current contents of
// the editor - reading the DOM directly would miss lines that Monaco
// hasn't rendered yet (it virtualizes long files).
//
// It talks to content.js purely via window.postMessage, since the two
// worlds cannot call each other's functions directly.

(function () {
  'use strict';

  var SOURCE_PAGE = 'lc-tracker-page';
  var SOURCE_CONTENT = 'lc-tracker-content';

  function getEditorCode() {
    // Preferred path: ask Monaco directly for the model's text. This is
    // complete and accurate regardless of scroll position.
    try {
      if (window.monaco && window.monaco.editor) {
        var models = window.monaco.editor.getModels();
        if (models && models.length) {
          var model = models[0];
          return {
            code: model.getValue(),
            lang: typeof model.getLanguageId === 'function' ? model.getLanguageId() : ''
          };
        }
      }
    } catch (err) {
      // fall through to the DOM fallback below
    }

    // Fallback: scrape whatever Monaco currently has painted to the DOM.
    // Only used if window.monaco isn't reachable for some reason (e.g.
    // LeetCode changes how the editor is bundled). This can be INCOMPLETE
    // for long solutions because Monaco only renders visible lines.
    try {
      var lineEls = document.querySelectorAll('.view-line');
      if (lineEls && lineEls.length) {
        var text = Array.prototype.map
          .call(lineEls, function (el) { return el.textContent; })
          .join('\n');
        return { code: text, lang: '' };
      }
    } catch (err2) {
      // ignore
    }

    return { code: '', lang: '' };
  }

  window.addEventListener('message', function (event) {
    if (event.source !== window) return;
    var data = event.data;
    if (!data || data.source !== SOURCE_CONTENT || data.type !== 'GET_CODE') return;

    var result = getEditorCode();
    window.postMessage(
      { source: SOURCE_PAGE, type: 'CODE_VALUE', code: result.code, lang: result.lang },
      '*'
    );
  });
})();
