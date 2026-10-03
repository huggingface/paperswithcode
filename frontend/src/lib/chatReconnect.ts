import { type ChatEvent, ChatTransportError, resumeChat } from "./chat";

const STREAM_RECONNECT_DELAYS_MS = [250, 500, 1_000] as const;

const waitForReconnect = (delayMs: number, signal: AbortSignal): Promise<void> => (
  new Promise((resolve) => {
    const finish = () => {
      window.clearTimeout(timer);
      signal.removeEventListener("abort", finish);
      resolve();
    };
    const timer = window.setTimeout(finish, delayMs);
    signal.addEventListener("abort", finish, { once: true });
  })
);

export async function* reconnectChatStream(
  initialSource: AsyncGenerator<ChatEvent>,
  options: {
    signal: AbortSignal;
    getSessionId: () => string | null;
    getAfterSequence: () => number;
    onSequence: (sequence: number) => void;
    onDisconnect: () => void;
  },
): AsyncGenerator<ChatEvent> {
  let source = initialSource;
  let reconnectAttempts = 0;
  for (;;) {
    let sawTerminalEvent = false;
    try {
      for await (const event of source) {
        if (event.type === "done" || event.type === "error") sawTerminalEvent = true;
        yield event;
      }
      if (sawTerminalEvent || options.signal.aborted) return;
      throw new ChatTransportError();
    } catch (error) {
      options.onDisconnect();
      const sessionId = options.getSessionId();
      if (
        options.signal.aborted
        || sawTerminalEvent
        || !(error instanceof ChatTransportError)
        || !sessionId
        || reconnectAttempts >= STREAM_RECONNECT_DELAYS_MS.length
      ) throw error;
      await waitForReconnect(
        STREAM_RECONNECT_DELAYS_MS[reconnectAttempts],
        options.signal,
      );
      if (options.signal.aborted) return;
      reconnectAttempts += 1;
      source = resumeChat(sessionId, {
        signal: options.signal,
        afterSequence: options.getAfterSequence(),
        onSequence: options.onSequence,
      });
    }
  }
}
