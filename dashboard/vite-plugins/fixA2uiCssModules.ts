import type { Plugin } from "vite";
import { readFileSync } from "node:fs";

const REPLACEMENTS: Array<[string, string]> = [
  [
    "var Text_default = {};",
    'var Text_default = {"a2uiText":"a2uiText","a2uiCaption":"a2uiCaption"};',
  ],
  [
    "var Button_default = {};",
    'var Button_default = {"button":"button","primary":"primary","borderless":"borderless"};',
  ],
  [
    "var TextField_default = {};",
    'var TextField_default = {"host":"host","label":"label","input":"input","invalid":"invalid","error":"error"};',
  ],
  [
    "var ChoicePicker_default = {};",
    'var ChoicePicker_default = {"host":"host","label":"label","filterInput":"filterInput","options":"options","chips":"chips","chip":"chip","selected":"selected","optionLabel":"optionLabel","optionText":"optionText"};',
  ],
];

export function applyA2uiCssModuleFixes(code: string): string {
  let next = code;
  for (const [from, to] of REPLACEMENTS) {
    next = next.replace(from, to);
  }
  return next;
}

function isA2uiV09Bundle(id: string): boolean {
  return id.includes("@a2ui/react") && id.includes("v0_9") && /\.(m?[jt]s|cjs)$/.test(id);
}

export function fixA2uiCssModules(): Plugin {
  return {
    name: "fix-a2ui-css-modules",
    enforce: "pre",
    transform(code, id) {
      if (!isA2uiV09Bundle(id)) return null;
      const patched = applyA2uiCssModuleFixes(code);
      if (patched === code) return null;
      return { code: patched, map: null };
    },
  };
}

export function fixA2uiCssModulesEsbuildPlugin() {
  return {
    name: "fix-a2ui-css-modules-esbuild",
    setup(build: { onLoad: (options: { filter: RegExp }, callback: (args: { path: string }) => { contents: string; loader: string } | undefined) => void }) {
      build.onLoad({ filter: /@a2ui\/react.*v0_9.*\.(m?js|cjs)$/ }, (args) => {
        const contents = readFileSync(args.path, "utf8");
        return {
          contents: applyA2uiCssModuleFixes(contents),
          loader: "js",
        };
      });
    },
  };
}
