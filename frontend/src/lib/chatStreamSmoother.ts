import type { ChatEvent } from "@/lib/chat";

const CHAT_STREAM_DEFAULTS = {
  minDelayMs: 5,
  maxDelayMs: 80,
  minRateCharsPerMs: 0.3,
  maxBufferedMs: 400,
  arrivalRateTauMs: 1_000,
  arrivalRateHeadroom: 1.1,
  maxPendingChars: 64,
} as const;

interface Clock {
  now(): number;
  sleep(ms: number, signal?: AbortSignal): Promise<void>;
}

export interface SmoothChatOptions {
  signal?: AbortSignal;
  clock?: Clock;
  isHidden?: () => boolean;
  minDelayMs?: number;
  maxDelayMs?: number;
  minRateCharsPerMs?: number;
  maxBufferedMs?: number;
  arrivalRateTauMs?: number;
  arrivalRateHeadroom?: number;
  maxPendingChars?: number;
}

export interface SmoothedChatStream {
  events: AsyncGenerator<ChatEvent>;
  takeAcceptedForStop(): ChatEvent[];
}

type DeltaType = "reasoning_delta" | "answer_delta";
type QueueItem =
  | { kind: "event"; event: ChatEvent; arrivedAt: number; chars: number }
  | { kind: "error"; error: unknown; arrivedAt: number; chars: 0 };

const defaultClock: Clock = {
  now: () => performance.now(),
  sleep: (ms, signal) => new Promise<void>((resolve) => {
    if (signal?.aborted || ms <= 0) {
      resolve();
      return;
    }
    const timer = window.setTimeout(done, ms);
    function done() {
      signal?.removeEventListener("abort", done);
      window.clearTimeout(timer);
      resolve();
    }
    signal?.addEventListener("abort", done, { once: true });
  }),
};

function isStructural(event: ChatEvent): boolean {
  return ![
    "stream_start",
    "sandbox_start",
    "sandbox_ready",
    "workspace_ready",
    "session_title_start",
    "session_title_delta",
    "session_title_done",
  ].includes(event.type);
}

/** Split complete semantic words while retaining the final incomplete word. */
export function takeCompletedText(
  text: string,
  force = false,
  maxPendingChars: number = CHAT_STREAM_DEFAULTS.maxPendingChars,
): { pieces: string[]; pending: string } {
  if (!text) return { pieces: [], pending: "" };
  if (force) return { pieces: [text], pending: "" };

  const Segmenter = (Intl as unknown as {
    Segmenter?: new (
      locales?: string | string[],
      options?: { granularity: "word" },
    ) => { segment(value: string): Iterable<{ index: number; isWordLike?: boolean }> };
  }).Segmenter;
  if (Segmenter) {
    const segments = [...new Segmenter(undefined, { granularity: "word" }).segment(text)];
    const words = segments.filter((segment) => segment.isWordLike);
    let cut = 0;
    if (words.length > 1) cut = words.at(-1)!.index;
    if (words.length && /\s$/u.test(text)) cut = text.length;
    if (cut > 0) {
      const complete = text.slice(0, cut);
      const pieces: string[] = [];
      const completeSegments = [...new Segmenter(undefined, { granularity: "word" }).segment(complete)];
      const completeWords = completeSegments.filter((segment) => segment.isWordLike);
      for (let index = 0; index < completeWords.length; index += 1) {
        const start = index === 0 ? 0 : completeWords[index].index;
        const end = completeWords[index + 1]?.index ?? complete.length;
        if (end > start) pieces.push(complete.slice(start, end));
      }
      if (!completeWords.length) pieces.push(complete);
      return { pieces, pending: text.slice(cut) };
    }
  } else {
    const matches = [...text.matchAll(/\s+/gu)];
    if (matches.length) {
      const pieces: string[] = [];
      let start = 0;
      for (const match of matches) {
        const end = match.index! + match[0].length;
        pieces.push(text.slice(start, end));
        start = end;
      }
      return { pieces, pending: text.slice(start) };
    }
  }

  if (text.length >= maxPendingChars) {
    return { pieces: [text.slice(0, maxPendingChars)], pending: text.slice(maxPendingChars) };
  }
  return { pieces: [], pending: text };
}

export function createSmoothedChatStream(
  source: AsyncGenerator<ChatEvent>,
  options: SmoothChatOptions = {},
): SmoothedChatStream {
  const config = {
    minDelayMs: options.minDelayMs ?? CHAT_STREAM_DEFAULTS.minDelayMs,
    maxDelayMs: options.maxDelayMs ?? CHAT_STREAM_DEFAULTS.maxDelayMs,
    minRateCharsPerMs: options.minRateCharsPerMs ?? CHAT_STREAM_DEFAULTS.minRateCharsPerMs,
    maxBufferedMs: options.maxBufferedMs ?? CHAT_STREAM_DEFAULTS.maxBufferedMs,
    arrivalRateTauMs: options.arrivalRateTauMs ?? CHAT_STREAM_DEFAULTS.arrivalRateTauMs,
    arrivalRateHeadroom: options.arrivalRateHeadroom ?? CHAT_STREAM_DEFAULTS.arrivalRateHeadroom,
    maxPendingChars: options.maxPendingChars ?? CHAT_STREAM_DEFAULTS.maxPendingChars,
  };
  const clock = options.clock ?? defaultClock;
  const queue: QueueItem[] = [];
  let pendingText = "";
  let pendingType: DeltaType | null = null;
  let pendingArrivedAt = 0;
  let accepting = true;
  let producerDone = false;
  let wake: (() => void) | null = null;
  let arrivalAccumulator = 0;
  let lastArrivalAt = clock.now();
  let firstDeltaAccepted = false;

  const notify = () => {
    wake?.();
    wake = null;
  };
  const enqueue = (event: ChatEvent, arrivedAt: number) => {
    const chars = event.type === "reasoning_delta" || event.type === "answer_delta"
      ? event.text.length
      : 0;
    queue.push({ kind: "event", event, arrivedAt, chars });
    notify();
  };
  const flushPending = (force: boolean) => {
    if (!pendingType || !pendingText) return;
    const split = takeCompletedText(pendingText, force, config.maxPendingChars);
    for (const text of split.pieces) {
      if (text) enqueue({ type: pendingType, text }, pendingArrivedAt);
      pendingArrivedAt = clock.now();
    }
    pendingText = split.pending;
    if (!pendingText) pendingType = null;
  };
  const accept = (event: ChatEvent) => {
    if (!accepting) return;
    const now = clock.now();
    if (event.type === "reasoning_delta" || event.type === "answer_delta") {
      const type = event.type;
      if (!event.text) return;
      if (!firstDeltaAccepted) {
        firstDeltaAccepted = true;
        arrivalAccumulator += event.text.length;
        lastArrivalAt = now;
        const firstCharacter = Array.from(event.text)[0];
        enqueue({ type, text: firstCharacter }, now);
        const remainder = event.text.slice(firstCharacter.length);
        if (remainder) {
          pendingType = type;
          pendingText = remainder;
          pendingArrivedAt = now;
          flushPending(false);
          while (pendingText.length >= config.maxPendingChars) flushPending(false);
        }
        return;
      }
      if (pendingType && pendingType !== type) flushPending(true);
      if (!pendingType) {
        pendingType = type;
        pendingArrivedAt = now;
      }
      pendingText += event.text;
      const elapsed = Math.max(0, now - lastArrivalAt);
      arrivalAccumulator *= Math.exp(-elapsed / config.arrivalRateTauMs);
      arrivalAccumulator += event.text.length;
      lastArrivalAt = now;
      flushPending(false);
      while (pendingText.length >= config.maxPendingChars) flushPending(false);
      return;
    }
    if (isStructural(event)) flushPending(true);
    enqueue(event, now);
  };

  const producer = (async () => {
    try {
      for await (const event of source) accept(event);
      if (accepting) flushPending(true);
    } catch (error) {
      if (accepting && !options.signal?.aborted) {
        flushPending(true);
        queue.push({ kind: "error", error, arrivedAt: clock.now(), chars: 0 });
      }
    } finally {
      producerDone = true;
      notify();
    }
  })();

  const waitForQueue = () => queue.length || producerDone
    ? Promise.resolve()
    : new Promise<void>((resolve) => { wake = resolve; });

  const events = (async function* (): AsyncGenerator<ChatEvent> {
    let lastEmissionAt = Number.NEGATIVE_INFINITY;
    try {
      for (;;) {
        await waitForQueue();
        if (!queue.length) {
          if (producerDone || !accepting) return;
          continue;
        }
        const item = queue[0];
        if (item.kind === "error") {
          queue.shift();
          throw item.error;
        }
        if (item.chars && !options.isHidden?.()) {
          const now = clock.now();
          const queuedChars = queue.reduce((total, candidate) => total + candidate.chars, 0);
          const oldest = queue.find((candidate) => candidate.chars)?.arrivedAt ?? now;
          const remaining = Math.max(0, config.maxBufferedMs - (now - oldest));
          const decayedArrival = arrivalAccumulator
            * Math.exp(-Math.max(0, now - lastArrivalAt) / config.arrivalRateTauMs)
            / config.arrivalRateTauMs;
          const catchUpRate = remaining > 0 ? queuedChars / remaining : Number.POSITIVE_INFINITY;
          const rate = Math.max(
            config.minRateCharsPerMs,
            decayedArrival * config.arrivalRateHeadroom,
            catchUpRate,
          );
          const normalDelay = Math.min(config.maxDelayMs, Math.max(config.minDelayMs, item.chars / rate));
          const deadlineDelay = Math.max(0, item.arrivedAt + config.maxBufferedMs - now);
          const desiredAt = Math.max(item.arrivedAt, lastEmissionAt + Math.min(normalDelay, deadlineDelay));
          await clock.sleep(Math.max(0, desiredAt - clock.now()), options.signal);
          if (!accepting || options.signal?.aborted) return;
        }
        queue.shift();
        lastEmissionAt = clock.now();
        yield item.event;
      }
    } finally {
      if (accepting) {
        accepting = false;
        notify();
        await source.return?.(undefined);
      }
      await producer;
    }
  })();

  return {
    events,
    takeAcceptedForStop() {
      if (!accepting) return [];
      accepting = false;
      if (pendingType && pendingText) {
        enqueue({ type: pendingType, text: pendingText }, pendingArrivedAt);
        pendingText = "";
        pendingType = null;
      }
      const accepted = queue.flatMap((item) => item.kind === "event"
        && item.event.type !== "done"
        && item.event.type !== "error" ? [item.event] : []);
      queue.length = 0;
      notify();
      void source.return?.(undefined);
      return accepted;
    },
  };
}
