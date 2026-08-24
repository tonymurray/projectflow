// Single entry point bundled into assets/codemirror/lib/codemirror-bundle.js.
// Exposes everything editor.html needs as one global, mirroring how the vendored
// Muya UMD bundle exposes itself as a browser global — see CLAUDE.md's Code Editor
// section for the regeneration process (this file is never shipped/run by the app
// itself, only its Rollup output is).
import { EditorState, Compartment } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { syntaxHighlighting, HighlightStyle } from "@codemirror/language";
import { tags } from "@lezer/highlight";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { php } from "@codemirror/lang-php";
import { basicSetup } from "codemirror";

window.PFCodeMirror = {
  EditorState,
  EditorView,
  Compartment,
  basicSetup,
  keymap,
  lineNumbers,
  defaultKeymap,
  history,
  historyKeymap,
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
