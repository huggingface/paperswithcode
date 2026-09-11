import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  fetchLiveTaskCatalog,
  loadPromptAsset,
  renderPrompt,
  taskCatalogForPrompt,
} from "../src/prompt.js";

test("cold prompt rendering uses the baked catalog while one live refresh runs", async () => {
  let resolveCatalog!: (value: string) => void;
  const pending = new Promise<string>((resolve) => {
    resolveCatalog = resolve;
  });
  let loads = 0;
  const load = () => {
    loads += 1;
    return pending;
  };
  const url = "https://catalog-background.example.test/api/v1";

  assert.equal(taskCatalogForPrompt(url, load), undefined);
  assert.equal(taskCatalogForPrompt(url, load), undefined);
  assert.equal(loads, 1);

  resolveCatalog("live catalog");
  await pending;
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(taskCatalogForPrompt(url, load), "live catalog");
  assert.equal(loads, 1);
});

test("failed background catalog refresh keeps using the baked catalog without retry churn", async () => {
  let loads = 0;
  const load = async () => {
    loads += 1;
    throw new Error("catalog unavailable");
  };
  const url = "https://catalog-cooldown.example.test/api/v1";

  assert.equal(taskCatalogForPrompt(url, load), undefined);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(taskCatalogForPrompt(url, load), undefined);

  assert.equal(loads, 1);
});

test("coalesces concurrent live task catalog loads and reuses the successful result", async () => {
  const originalFetch = globalThis.fetch;
  let requests = 0;
  globalThis.fetch = async () => {
    requests += 1;
    return {
      ok: true,
      async json() {
        return {
          results: [{ name: "Text Reranking", slug: "text-reranking" }],
          next_page: null,
        };
      },
    } as Response;
  };
  try {
    const url = "https://catalog-coalescing.example.test/api/v1";
    const [first, second] = await Promise.all([
      fetchLiveTaskCatalog(url),
      fetchLiveTaskCatalog(url),
    ]);
    const third = await fetchLiveTaskCatalog(url);

    assert.equal(requests, 1);
    assert.equal(first, second);
    assert.equal(second, third);
    assert.match(third, /`text-reranking` — Text Reranking/u);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("does not cache a failed live task catalog load", async () => {
  const originalFetch = globalThis.fetch;
  let requests = 0;
  globalThis.fetch = async () => {
    requests += 1;
    return {
      ok: requests > 1,
      status: requests > 1 ? 200 : 503,
      async json() {
        return {
          results: [{ name: "Image Classification", slug: "image-classification" }],
          next_page: null,
        };
      },
    } as Response;
  };
  try {
    const url = "https://catalog-retry.example.test/api/v1";
    await assert.rejects(fetchLiveTaskCatalog(url), /request failed: 503/u);
    const catalog = await fetchLiveTaskCatalog(url);

    assert.equal(requests, 2);
    assert.match(catalog, /`image-classification` — Image Classification/u);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("loads the immutable external-worker prompt path from the launcher environment", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "pwc-prompt-"));
  const promptPath = path.join(directory, "pi-system-prompt.txt");
  const previous = process.env.PWC_EXTERNAL_PI_PROMPT_PATH;
  await writeFile(promptPath, "immutable external prompt", "utf8");
  process.env.PWC_EXTERNAL_PI_PROMPT_PATH = promptPath;
  try {
    assert.equal(await loadPromptAsset(), "immutable external prompt");
  } finally {
    if (previous === undefined) delete process.env.PWC_EXTERNAL_PI_PROMPT_PATH;
    else process.env.PWC_EXTERNAL_PI_PROMPT_PATH = previous;
    await rm(directory, { recursive: true });
  }
});

test("renders the trusted reader-mode metadata independently of paper evidence", async () => {
  const source = [
    "system reader-v1",
    '<turn_metadata>{"web_search_enabled":false,"reader_mode":false}</turn_metadata>',
  ].join("\n");

  const prompt = await renderPrompt({
    model: "model-a",
    hfUsername: "reviewer",
    webSearchEnabled: false,
    readerMode: true,
    source,
  });

  assert.match(prompt, /"reader_mode":true/);
  assert.doesNotMatch(prompt, /"reader_mode":false/);
});

test("replaces the baked task catalog with the live catalog", async () => {
  const source = [
    "before",
    "<!-- PWC_TASK_CATALOG_START -->",
    "stale task catalog",
    "<!-- PWC_TASK_CATALOG_END -->",
    "after",
  ].join("\n");

  const prompt = await renderPrompt({
    model: "model-a",
    hfUsername: "reviewer",
    webSearchEnabled: false,
    readerMode: false,
    taskCatalog: "## Complete live task lookup index\n\n- `text-reranking` — Text Reranking",
    source,
  });

  assert.doesNotMatch(prompt, /stale task catalog/);
  assert.match(prompt, /`text-reranking` — Text Reranking/);
});

test("keeps the shared paper prompt behind the trusted paper flag", async () => {
  const source = [
    "before",
    "## Private paper authoring (paper-v1)",
    "paper-specific instructions",
    "## Task",
    "after",
  ].join("\n");

  const disabled = await renderPrompt({
    model: "model-a", hfUsername: "reviewer", webSearchEnabled: false, readerMode: false, source,
  });
  const enabled = await renderPrompt({
    model: "model-a", hfUsername: "reviewer", webSearchEnabled: false, readerMode: false,
    paperArtifactsEnabled: true, paperGuide: "guide", source,
  });

  assert.doesNotMatch(disabled, /paper-specific instructions/);
  assert.match(enabled, /paper-specific instructions/);
});
