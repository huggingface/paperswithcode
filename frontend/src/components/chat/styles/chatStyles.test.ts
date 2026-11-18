import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const styleDirectory = resolve(process.cwd(), "src/components/chat/styles");
const styleNames = [
  "composer",
  "conversation",
  "dialogs",
  "layout",
  "navigation",
  "notices",
  "previews",
  "primitives",
  "shared",
  "sharing",
];
const featureStyles = styleNames.map((name) => (
  readFileSync(resolve(styleDirectory, `${name}.css`), "utf8")
)).join("\n");
const globalStyles = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

describe("chat style ownership", () => {
  it("keeps critical surfaces in focused feature styles, not the global sheet", () => {
    for (const selector of [
      ".chat-page",
      ".chat-sidebar",
      ".chat-conversation",
      ".chat-composer",
      ".chat-capacity-dialog",
      ".chat-share-dialog",
      ".shared-chat-page",
    ]) {
      expect(featureStyles).toContain(selector);
    }
    expect(globalStyles).not.toMatch(
      /\.(?:chat-|shared-chat-|paper-preview-|web-preview-|github-preview-|hf-preview-)/,
    );
  });

  it("retains responsive and accessibility behavior beside its owners", () => {
    expect(featureStyles).toContain("@media (max-width: 900px)");
    expect(featureStyles).toContain("@media (max-width: 640px)");
    expect(featureStyles).toContain("@media (max-width: 560px)");
    expect(featureStyles).toContain("@media (prefers-reduced-motion: reduce)");
    expect(featureStyles).toContain("@media (forced-colors: active)");
    expect(featureStyles).toContain("@media (hover: none), (pointer: coarse)");
  });

  it("aligns the desktop header brand with the chat navigation column", () => {
    expect(globalStyles).toContain("--app-leading-column-width: 280px");
    expect(globalStyles).toContain("width: var(--app-leading-column-width)");
    expect(featureStyles).toContain("width: var(--app-leading-column-width)");
  });

  it("keeps inline Excalidraw frames at the App 4:3 aspect", () => {
    expect(featureStyles).toContain("aspect-ratio: 4 / 3");
    expect(featureStyles).toContain(".chat-mcp-app-fullscreen iframe { height: calc(100vh - 72px) !important; aspect-ratio: auto; }");
  });
});

describe("chat style loading", () => {
  const source = (path: string) => readFileSync(resolve(process.cwd(), path), "utf8");

  it("loads the chat sheet only with chat surfaces; link previews stay global", () => {
    const main = source("src/main.tsx");
    expect(main).not.toContain("chat/styles/index.css");
    expect(main).toContain('import "./components/chat/styles/previews.css";');
    expect(source("src/components/chat/styles/index.css")).not.toContain("previews.css");
    for (const view of ["ChatView", "SharedChatView", "FeedView", "PaperReaderView"]) {
      expect(source(`src/views/${view}.tsx`)).toContain('import "@/components/chat/styles/index.css";');
    }
  });
});
