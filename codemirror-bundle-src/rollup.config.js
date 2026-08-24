import { nodeResolve } from "@rollup/plugin-node-resolve";
import terser from "@rollup/plugin-terser";

export default {
  input: "entry.js",
  output: {
    file: "dist/codemirror-bundle.js",
    format: "iife",
    name: "PFCodeMirrorBundle",
  },
  plugins: [nodeResolve(), terser()],
};
