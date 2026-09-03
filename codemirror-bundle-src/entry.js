// Single entry point bundled into assets/codemirror/lib/codemirror-bundle.js.
// Exposes everything editor.html needs as one global, mirroring how the vendored
// Muya UMD bundle exposes itself as a browser global — see CLAUDE.md's Code Editor
// section for the regeneration process (this file is never shipped/run by the app
// itself, only its Rollup output is).
import { EditorState, Compartment, Prec } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap, copyLineDown, selectLine } from "@codemirror/commands";
import { gotoLine } from "@codemirror/search";
import { syntaxHighlighting, HighlightStyle } from "@codemirror/language";
import { tags } from "@lezer/highlight";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { php } from "@codemirror/lang-php";
import { basicSetup } from "codemirror";

// nano-style "cut current line": select the whole line (selectLine already extends
// the selection through the trailing newline, so the kill removes the line cleanly)
// then hand off to the browser's native cut. CodeMirror listens for the DOM "cut"
// event itself (@codemirror/view has a built-in handler for it) and syncs the
// resulting deletion back into its own document model — the same path a manual
// mouse-selection + native Ctrl+X already goes through, so this needs no manual
// clipboard-API call and no manual dispatch to remove the text ourselves.
const cutLine = view => {
  if (!selectLine(view)) return false;
  document.execCommand("cut");
  return true;
};

window.PFCodeMirror = {
  EditorState,
  EditorView,
  Compartment,
  Prec,
  basicSetup,
  keymap,
  lineNumbers,
  defaultKeymap,
  history,
  historyKeymap,
  gotoLine,
  copyLineDown,
  cutLine,
  syntaxHighlighting,
  HighlightStyle,
  tags,
  languages: {
    js: javascript,
    py: python,
    html: html,
    css: css,
    php: php,
  },
};
