import { describe, expect, it } from "vitest";
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
});
