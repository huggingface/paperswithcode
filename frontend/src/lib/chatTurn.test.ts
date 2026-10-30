import { describe, expect, it, vi } from "vitest";
import { ChatStreamError } from "./chat";
import { ChatTurn } from "./chatTurn";

describe("ChatTurn terminal ownership", () => {
  it.each(["openrouter_unavailable", "hf_inference_billing_exhausted"])(
    "classifies %s consistently across SSE and HTTP failures", (code) => {
      const streamed = new ChatTurn();
      const rejected = new ChatTurn();
      for (const turn of [streamed, rejected]) turn.start([], "session-1");
      expect(streamed.observe({ type: "error", message: "Unavailable", code })).toBe(true);
      expect(rejected.reject(new ChatStreamError("Unavailable", code), false)).toBe("provider");
      for (const turn of [streamed, rejected]) {
        expect(turn.shouldRefreshProvider).toBe(true);
        expect(turn.streamFailed).toBe(true);
        expect(turn.admissionRejected).toBe(false);
      }
    },
  );

  it("clears terminal and admission outcomes when retry starts", () => {
    const turn = new ChatTurn();
    turn.start([], null);
    turn.reject(new ChatStreamError("Full", "chat_capacity"), false);
    expect(turn.admissionRejected).toBe(true);
    turn.finish();
    turn.start([], "session-2");
    expect(turn.busy).toBe(true);
    expect(turn.sessionId).toBe("session-2");
    expect(turn.admissionRejected).toBe(false);
    expect(turn.streamFailed).toBe(false);
    expect(turn.sawTerminalEvent).toBe(false);
  });

  it("does not treat a completed reconnect as a failed turn", () => {
    const turn = new ChatTurn();
    turn.start([], "session-1");
    expect(turn.reject(new ChatStreamError("Idle", "chat_not_busy"), true)).toBe("completed");
    expect(turn.streamFailed).toBe(false);
    expect(turn.admissionRejected).toBe(false);
  });

  it("keeps one phase from start to settlement", () => {
    const turn = new ChatTurn();
    expect(turn.phase).toEqual({ status: "idle" });
    turn.start([], "session-1");
    turn.observe({ type: "stream_start", request_id: "request-1", session_id: "session-1" });
    expect(turn.phase).toMatchObject({ status: "streaming", streamStart: { providerExecuted: true }, terminal: "pending" });
    turn.observe({ type: "done" });
    turn.finish();
    expect(turn.phase).toMatchObject({ status: "settled", terminal: "complete" });
    expect(turn.busy).toBe(false);
    expect(turn.sawTerminalEvent).toBe(true);
    expect(turn.streamFailed).toBe(false);

    turn.start([], "session-1");
    turn.observe({ type: "error", message: "Failed", code: "provider_error" });
    expect(turn.phase).toMatchObject({ status: "streaming", terminal: "error" });
    expect(turn.streamFailed).toBe(true);
    expect(turn.shouldRefreshProvider).toBe(false);
  });

  it("notifies subscribers only when the shown conversation changes", () => {
    const turn = new ChatTurn();
    const listener = vi.fn();
    turn.subscribe(listener);
    const before = turn.getSnapshot();
    turn.restore([{ id: "m1", role: "user", text: "Hidden" }]);
    expect(listener).not.toHaveBeenCalled();
    expect(turn.getSnapshot()).toBe(before);
    turn.restore([{ id: "m1", role: "user", text: "Shown" }], { show: true, view: { sessionError: "" } });
    expect(listener).toHaveBeenCalledTimes(1);
    expect(turn.getSnapshot().messages).toEqual([{ id: "m1", role: "user", text: "Shown" }]);
  });
});
