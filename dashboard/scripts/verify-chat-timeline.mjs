import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { execFileSync } from "node:child_process";

const root = new URL("..", import.meta.url);
const rootPath = root.pathname;
const outDir = mkdtempSync(join(tmpdir(), "emperor-timeline-verify-"));

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
      "src/utils/chatTimeline.ts",
    ],
    { cwd: rootPath, stdio: "inherit" }
  );

  const mod = await import(pathToFileURL(join(outDir, "utils/chatTimeline.js")).href);
  const { buildTimelineFromEvents, buildTimelineFromStoredMessages } = mod;

  const eventTimeline = buildTimelineFromEvents([
    { type: "message", message: { role: "user", content: [{ type: "text", text: "u" }], timestamp: 1000 } },
    {
      type: "message",
      message: {
        role: "assistant",
        content: [
          { type: "thinking", thinking: "a" },
          { type: "text", text: "preface" },
          { type: "toolCall", name: "render_a2ui" },
        ],
        timestamp: 2000,
      },
    },
    { type: "message", message: { role: "tool", content: [{ type: "text", text: "ok" }], timestamp: 3000 } },
    {
      type: "message",
      message: {
        role: "assistant",
        content: [
          { type: "thinking", thinking: "b" },
          {
            type: "a2ui",
            surfaceId: "s1",
            messages: [{ createSurface: { surfaceId: "s1" } }, { updateComponents: { surfaceId: "s1" } }],
          },
        ],
        timestamp: 4000,
      },
    },
  ]);

  assert.equal(eventTimeline.length, 4);
  assert.equal(eventTimeline[1].kind, "message");
  assert.equal(eventTimeline[2].kind, "process");
  assert.equal(eventTimeline[3].kind, "message");
  assert.equal(eventTimeline[3].role, "assistant");
  assert.equal(eventTimeline[3].a2uiSurfaces?.length, 1);
  assert.equal(eventTimeline[3].a2uiSurfaces?.[0]?.messages.length, 2);
  assert.equal(eventTimeline[2].group.steps.length, 3);
  assert.match(eventTimeline[2].group.steps[1].text, /Done: render_a2ui/);

  const storedTimeline = buildTimelineFromStoredMessages([
    { role: "user", content: "u", created_at: 1 },
    {
      role: "assistant",
      content: "preface",
      _thinking: "a",
      tool_calls: [{ function: { name: "render_a2ui" } }],
      created_at: 2,
    },
    { role: "tool", content: "ok", created_at: 3 },
    {
      role: "assistant",
      _thinking: "b",
      a2ui_messages: [{ createSurface: { surfaceId: "s1" } }, { updateComponents: { surfaceId: "s1" } }],
      a2ui_surface_id: "s1",
      created_at: 4,
    },
  ]);

  assert.deepEqual(storedTimeline, eventTimeline);

  const legacyEventTimeline = buildTimelineFromEvents([
    { type: "message", message: { role: "user", content: [{ type: "text", text: "u" }], timestamp: 1000 } },
    {
      type: "message",
      message: {
        role: "assistant",
        content: "legacy preface",
        _thinking: "legacy-think",
        tool_calls: [{ function: { name: "cron" } }],
        timestamp: 2000,
      },
    },
    { type: "message", message: { role: "tool", content: [{ type: "text", text: "ok" }], timestamp: 3000 } },
    {
      type: "message",
      message: {
        role: "assistant",
        content: "legacy final",
        timestamp: 4000,
      },
    },
  ]);

  assert.equal(legacyEventTimeline[1].kind, "message");
  assert.equal(legacyEventTimeline[1].content, "legacy preface");
  assert.equal(legacyEventTimeline[2].kind, "process");
  assert.match(legacyEventTimeline[2].group.steps[0].text, /legacy-think/);
  assert.match(legacyEventTimeline[2].group.steps[1].text, /Done: cron/);
  assert.equal(legacyEventTimeline[3].kind, "message");
  assert.equal(legacyEventTimeline[3].content, "legacy final");

  const noDuplicateTimeline = buildTimelineFromStoredMessages([
    { role: "user", content: "u", created_at: 1 },
    {
      role: "assistant",
      content: "same final",
      tool_calls: [{ function: { name: "web_search" } }],
      created_at: 2,
    },
    { role: "tool", content: "ok", created_at: 3 },
    {
      role: "assistant",
      content: "same final",
      created_at: 4,
    },
  ]);

  assert.equal(noDuplicateTimeline.length, 3);
  assert.equal(noDuplicateTimeline[1].kind, "process");
  assert.equal(noDuplicateTimeline[2].kind, "message");
  assert.equal(noDuplicateTimeline[2].content, "same final");
  console.log("verify-chat-timeline: ok");
} finally {
  rmSync(outDir, { recursive: true, force: true });
}
