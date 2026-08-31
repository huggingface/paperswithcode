import assert from "node:assert/strict";
import { once } from "node:events";
import { readdir } from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import test from "node:test";

import { createExternalWorkerServer } from "../src/external_server.js";
import {
  prewarmExternalWorker,
  prewarmExternalWorkerAndListen,
} from "../src/external_startup.js";
import { handleExternalFrame } from "../src/external_worker.js";

const profile = {
  prompt: "startup-sensitive-profile-value",
  tool_names: ["bash", "read"],
};

async function shadowRoots(): Promise<Set<string>> {
  return new Set(
    (await readdir(os.tmpdir()))
      .filter((name) => name.startsWith("pwc-external-pi-shadow-")),
  );
}

async function within<T>(promise: Promise<T>, milliseconds: number): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => reject(new Error("prewarm startup timed out")), milliseconds);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

for (const maximumConcurrent of [8, 32]) {
  test(`startup completes all ${maximumConcurrent} prewarms before listening`, async () => {
    let active = 0;
    let peak = 0;
    let completed = 0;
    let release!: () => void;
    const barrier = new Promise<void>((resolve) => { release = resolve; });
    let resolveStarted!: () => void;
    const allStarted = new Promise<void>((resolve) => { resolveStarted = resolve; });
    const events: string[] = [];

    const starting = prewarmExternalWorkerAndListen({
      maximumConcurrent,
      profile,
      listen: () => { events.push("listen"); },
      handleFrame: async () => {
        active += 1;
        peak = Math.max(peak, active);
        if (active === maximumConcurrent) resolveStarted();
        await barrier;
        active -= 1;
        completed += 1;
        events.push("prewarm");
        return undefined;
      },
    });

    await within(allStarted, 5_000);
    assert.equal(events.includes("listen"), false);
    release();
    await starting;

    assert.equal(peak, maximumConcurrent);
    assert.equal(completed, maximumConcurrent);
    assert.equal(events.at(-1), "listen");
  });
}

test("startup settles every prewarm and never listens when one fails", async () => {
  const maximumConcurrent = 8;
  let settled = 0;
  let listened = false;

  await assert.rejects(
    prewarmExternalWorkerAndListen({
      maximumConcurrent,
      profile,
      listen: () => { listened = true; },
      handleFrame: async (_frame, _profile, ordinal) => {
        await new Promise((resolve) => setTimeout(resolve, ordinal));
        settled += 1;
        if (ordinal === 0) throw new Error("synthetic failure");
        return undefined;
      },
    }),
    /prewarm failed/i,
  );

  assert.equal(settled, maximumConcurrent);
  assert.equal(listened, false);
});

test("prewarm sends a content-free 2,000-entry frame through the real handler", async () => {
  const before = await shadowRoots();
  let observedFrame: Record<string, unknown> | undefined;

  await prewarmExternalWorker({
    maximumConcurrent: 1,
    profile,
    handleFrame: async (frame, workerProfile) => {
      observedFrame = frame as Record<string, unknown>;
      return handleExternalFrame(frame, workerProfile);
    },
  });

  assert(observedFrame);
  const entries = observedFrame.transcript_entries as Record<string, unknown>[];
  assert.equal(observedFrame.type, "shadow_compare");
  assert.equal(entries.length, 2_000);
  assert.equal(entries[0]?.type, "session");
  assert.equal(entries[1]?.parentId, null);
  assert.equal(entries.at(-1)?.parentId, entries.at(-2)?.id);
  assert.doesNotMatch(
    JSON.stringify(observedFrame),
    /startup-sensitive-profile-value|question text|answer text|secret value/i,
  );
  assert.deepEqual(await shadowRoots(), before);
});

test("successful prewarm exposes a ready server with no sessions or operations", async () => {
  const token = "s".repeat(32);
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 2,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile,
  });

  await prewarmExternalWorkerAndListen({
    maximumConcurrent: 2,
    profile,
    listen: () => server.listen(0, "127.0.0.1"),
  });
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  try {
    const status = await (await fetch(`http://127.0.0.1:${address.port}/v1/status`, {
      headers: { Authorization: `Bearer ${token}` },
    })).json() as any;
    assert.equal(status.active_sessions, 0);
    assert.deepEqual(status.operation_counters, {
      shadow_requests: 0,
      model_calls: 0,
      tool_calls: 0,
      provider_calls: 0,
      modal_calls: 0,
      billing_events: 0,
    });
  } finally {
    server.close();
    await once(server, "close");
  }
});
