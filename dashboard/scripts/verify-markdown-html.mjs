import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const root = new URL("..", import.meta.url);
const rootPath = root.pathname;
const outDir = mkdtempSync(join(tmpdir(), "emperor-markdown-verify-"));
const localPatchedPath = join(rootPath, ".tmpverify/MarkdownContent.no-css.mjs");

try {
  execFileSync(
    join(rootPath, "node_modules/.bin/tsc"),
    [
      "--module",
      "ESNext",
      "--moduleResolution",
      "bundler",
      "--target",
      "ES2020",
      "--jsx",
      "react-jsx",
      "--esModuleInterop",
      "--skipLibCheck",
      "--outDir",
      outDir,
      "src/components/chat/MarkdownContent.tsx",
    ],
    { cwd: rootPath, stdio: "inherit" }
  );

  const builtPath = join(outDir, "MarkdownContent.js");
  const patchedPath = localPatchedPath;
  mkdirSync(dirname(patchedPath), { recursive: true });
  const built = readFileSync(builtPath, "utf8")
    .split("\n")
    .filter((line) => !line.includes("highlight.js/styles/github.min.css"))
    .join("\n");
  writeFileSync(patchedPath, built);

  const { default: MarkdownContent } = await import(pathToFileURL(patchedPath).href);

  const safe = renderToStaticMarkup(
    React.createElement(MarkdownContent, {
      content: "<div><strong>ok</strong></div>",
      allowHtml: true,
    })
  );
  assert.match(safe, /<div><strong>ok<\/strong><\/div>/);

  const unsafe = renderToStaticMarkup(
    React.createElement(MarkdownContent, {
      content: "<script>alert(1)</script><img src=\"https://x.test/a.png\" onerror=\"alert(1)\" />",
      allowHtml: true,
    })
  );
  assert.doesNotMatch(unsafe, /script/i);
  assert.doesNotMatch(unsafe, /onerror/i);
  assert.match(unsafe, /<img src="https:\/\/x\.test\/a\.png"/);

  console.log("verify-markdown-html: ok");
} finally {
  rmSync(outDir, { recursive: true, force: true });
  rmSync(localPatchedPath, { force: true });
}
