import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ChatStreamError,
  ChatTransportError,
  isChatSmoothStreamingEnabled,
  reportChatLatency,
  resumeChat,
  streamChat,
} from "@/lib/chat";

describe("smooth streaming kill switch", () => {
  it.each(["0", "false", "off", "no", " FALSE "])("disables smoothing for %s", (value) => {
    vi.stubEnv("VITE_CHAT_SMOOTH_STREAMING", value);
    expect(isChatSmoothStreamingEnabled()).toBe(false);
  });

  it.each([undefined, "", "1", "true", "yes"])("defaults smoothing on for %s", (value) => {
    vi.stubEnv("VITE_CHAT_SMOOTH_STREAMING", value);
    expect(isChatSmoothStreamingEnabled()).toBe(true);
  });
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("reportChatLatency", () => {
  it("posts same-origin best-effort timing without affecting the caller", async () => {
    vi.stubEnv("VITE_CHAT_LIVE", "1");
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    reportChatLatency("request/id", {
      submission_to_stream_start_ms: 125.5,
    });

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/chat/latency/request%2Fid"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        keepalive: true,
        body: JSON.stringify({ submission_to_stream_start_ms: 125.5 }),
      }),
    );
  });

  it("swallows reporting failures", async () => {
    vi.stubEnv("VITE_CHAT_LIVE", "1");
    const fetchMock = vi.fn().mockRejectedValue(new Error("offline"));
    vi.stubGlobal("fetch", fetchMock);

    expect(() => reportChatLatency(
      "r1",
      { terminal_classification: "network_error" },
    )).not.toThrow();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });
});

describe("streamChat access failures", () => {
  it("types a failed fetch as a retryable transport interruption", async () => {
    vi.stubEnv("VITE_CHAT_LIVE", "1");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("connection reset")));

    const events = streamChat({
      message: "Reconnect me",
      session_id: "session-1",
      client_message_id: "message-transport",
      web_search_enabled: false,
    });

    await expect(events.next()).rejects.toBeInstanceOf(ChatTransportError);
  });

  it("uses the canonical stale-auth notification for an expired session", async () => {
    vi.stubEnv("VITE_CHAT_LIVE", "1");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: "Not authenticated",
    }), { status: 401 })));
    const stale = vi.fn();
    window.addEventListener("pwc:auth-stale", stale);

    const events = streamChat({
      message: "Auth check",
      session_id: null,
      client_message_id: "message-auth",
      web_search_enabled: false,
    });

    await expect(events.next()).rejects.toMatchObject({ status: 401 });
    expect(stale).toHaveBeenCalledOnce();
    window.removeEventListener("pwc:auth-stale", stale);
  });

  it("keeps PwC capacity and Retry-After separate from provider errors", async () => {
    vi.stubEnv("VITE_CHAT_LIVE", "1");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: { code: "chat_capacity", message: "Research capacity is occupied" },
    }), {
      status: 429,
      headers: { "Content-Type": "application/json", "Retry-After": "7" },
    })));

    const events = streamChat({
      message: "Capacity check",
      session_id: null,
      client_message_id: "message-capacity",
      web_search_enabled: false,
    });

    await expect(events.next()).rejects.toMatchObject({
      code: "chat_capacity",
      status: 429,
      retryAfterSeconds: 7,
    } satisfies Partial<ChatStreamError>);
  });

  it("turns an unstructured staging 403 into an actionable error", async () => {
    vi.stubEnv("VITE_CHAT_LIVE", "1");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Forbidden", {
      status: 403,
      headers: { "Content-Type": "text/plain" },
    })));

    const events = streamChat({
      message: "Continue from a shared chat",
      session_id: null,
      client_message_id: "message-1",
      web_search_enabled: false,
    });

    await expect(events.next()).rejects.toMatchObject({
      name: "ChatStreamError",
      code: "staging_access_required",
      message: expect.stringContaining("limited to approved Hugging Face users"),
    } satisfies Partial<ChatStreamError>);
  });
});

describe("resumeChat", () => {
  it("uses the authenticated session reconnect stream and parses replayed events", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      `data: ${JSON.stringify({ type: "answer_delta", text: "replayed" })}\n\n`,
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    ));
    vi.stubGlobal("fetch", fetchMock);

    const events = resumeChat("session/id");

    await expect(events.next()).resolves.toEqual({
      done: false,
      value: { type: "answer_delta", text: "replayed" },
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/chat/sessions/session%2Fid/stream"),
      expect.objectContaining({ method: "GET", credentials: "include" }),
    );
  });

  it("carries the latest SSE id privately and skips stale replay frames", async () => {
    const seenSequences: number[] = [];
    const fetchMock = vi.fn().mockResolvedValue(new Response([
      `id: 13\nevent: answer_delta\ndata: ${JSON.stringify({ type: "answer_delta", text: "new" })}\n\n`,
      `id: 13\nevent: answer_delta\ndata: ${JSON.stringify({ type: "answer_delta", text: "duplicate" })}\n\n`,
      `id: 12\nevent: answer_delta\ndata: ${JSON.stringify({ type: "answer_delta", text: "older" })}\n\n`,
      `id: 14\nevent: done\ndata: ${JSON.stringify({ type: "done", finish_reason: "success" })}\n\n`,
    ].join(""), {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const events = resumeChat("session-1", {
      afterSequence: 12,
      onSequence: (sequence) => seenSequences.push(sequence),
    });

    const received = [];
    for await (const event of events) received.push(event);
    expect(received).toEqual([
      { type: "answer_delta", text: "new" },
      { type: "done", finish_reason: "success" },
    ]);
    expect(seenSequences).toEqual([13, 14]);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/chat/sessions/session-1/stream");
    expect(init.method).toBe("GET");
    expect(new Headers(init.headers).get("Last-Event-ID")).toBe("12");
  });
});
