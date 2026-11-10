/**
 * Microphone → same-origin WebSocket relay → streaming transcript.
 *
 * The microphone is opened before the ticket is requested, because the ticket
 * expires 30 s after issue and a permission prompt can take longer. Audio is
 * buffered until the socket opens. Stopping flushes the last audio, asks the
 * provider to transcribe what remains, and waits briefly for the final text.
 */

import { useQuery } from "@tanstack/react-query";
import React from "react";

import { ApiError } from "@/lib/apiTransport";
import { dictationApi, type DictationSession } from "@/lib/api/dictation";
import { getApiOrigin, isChatEnabled } from "@/lib/apiUrl";
import { createProtocol, type DictationProtocol } from "@/lib/dictation/protocol";
import workletSource from "@/lib/dictation/pcmCapture.worklet.js?raw";

export type DictationPhase = "idle" | "connecting" | "recording" | "finishing";

const FINAL_TEXT_TIMEOUT_MS = 5_000;
const STATUS_POLL_MS = 5_000;

export function dictationSupported(): boolean {
  return typeof window !== "undefined"
    && Boolean(navigator.mediaDevices?.getUserMedia)
    && typeof AudioWorkletNode !== "undefined"
    && typeof WebSocket !== "undefined";
}

/** Voice-input availability; for signed-in users this also warms the model. */
export function useDictationStatus() {
  const enabled = isChatEnabled() && dictationSupported();
  return useQuery({
    queryKey: ["dictationStatus"],
    queryFn: () => dictationApi.getStatus(),
    enabled,
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 30_000,
    // While the endpoint wakes up or is full, poll so the mic turns on again.
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.signed_in && !data.provider && (data.reason === "starting" || data.reason === "busy")
        ? STATUS_POLL_MS
        : false;
    },
  });
}

// Load the worklet from a Blob URL: Vite inlines small `?url` assets as
// data: URLs, which Safari does not accept in audioWorklet.addModule().
let workletUrl: string | undefined;
function pcmWorkletUrl(): string {
  workletUrl ??= URL.createObjectURL(new Blob([workletSource], { type: "text/javascript" }));
  return workletUrl;
}

function toBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

function socketUrl(path: string): string {
  const url = new URL(path, getApiOrigin() || window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export function dictationErrorMessage(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError" || error.name === "SecurityError") {
      return "Microphone access is blocked. Allow it in your browser's site settings, then try again.";
    }
    if (error.name === "NotFoundError") return "No microphone was found.";
    if (error.name === "NotReadableError") return "The microphone is in use by another app.";
  }
  if (error instanceof ApiError) {
    const code = (error.detail as { code?: string } | undefined)?.code;
    if (code === "daily_limit") return "You've used today's voice input. It resets at midnight UTC.";
    if (code === "already_dictating") return "Voice input is already running in another tab.";
    if (code === "starting") return "Voice input is starting up. Try again in a minute.";
    if (code === "busy") return "Voice input is busy. Try again in a moment.";
    if (error.status === 401) return "Sign in to use voice input.";
  }
  if (error instanceof Error && error.message) return error.message;
  return "Voice input failed. Try again.";
}

interface Resources {
  stream?: MediaStream;
  context?: AudioContext;
  node?: AudioWorkletNode;
  socket?: WebSocket;
  protocol?: DictationProtocol;
  session?: DictationSession;
  queue: string[];
  startedAt: number;
  timers: number[];
  finishing: boolean;
  settled: boolean;
}

interface UseDictationOptions {
  /** Appends transcribed text as it streams in. */
  onText: (delta: string) => void;
  /** The session ended: `cancelled` when the user discarded it. */
  onEnd?: (outcome: { cancelled: boolean; error?: string }) => void;
}

export function useDictation({ onText, onEnd }: UseDictationOptions) {
  const [phase, setPhase] = React.useState<DictationPhase>("idle");
  const [elapsed, setElapsed] = React.useState(0);
  const [maxSeconds, setMaxSeconds] = React.useState(0);
  const [level, setLevel] = React.useState(0);
  const resources = React.useRef<Resources | null>(null);
  const callbacks = React.useRef({ onText, onEnd });
  callbacks.current = { onText, onEnd };

  const release = React.useCallback((outcome: { cancelled: boolean; error?: string }, unmounting = false) => {
    const current = resources.current;
    if (!current || current.settled) return;
    current.settled = true;
    resources.current = null;
    current.timers.forEach((timer) => window.clearTimeout(timer));
    current.stream?.getTracks().forEach((track) => track.stop());
    current.node?.port.close();
    void current.context?.close().catch(() => undefined);
    if (current.socket && current.socket.readyState <= WebSocket.OPEN) current.socket.close(1000);
    if (current.session) {
      const seconds = (performance.now() - current.startedAt) / 1000;
      void dictationApi.finishSession(current.session.session_id, seconds).catch(() => undefined);
    }
    if (unmounting) return;
    setPhase("idle");
    setLevel(0);
    setElapsed(0);
    callbacks.current.onEnd?.(outcome);
  }, []);

  const finish = React.useCallback(() => {
    const current = resources.current;
    if (!current || current.settled || current.finishing) return;
    current.finishing = true;
    window.clearTimeout(current.timers[0]);
    if (!current.socket || current.socket.readyState !== WebSocket.OPEN || !current.protocol) {
      release({ cancelled: false });
      return;
    }
    setPhase("finishing");
    current.stream?.getTracks().forEach((track) => track.stop());
    // The worklet answers "flush" with the partial last chunk; then ask the
    // provider for the remaining text.
    current.node?.port.postMessage("flush");
    current.timers.push(window.setTimeout(() => release({ cancelled: false }), FINAL_TEXT_TIMEOUT_MS));
  }, [release]);

  const cancel = React.useCallback(() => release({ cancelled: true }), [release]);

  const start = React.useCallback(async () => {
    if (resources.current) return;
    // timers[0] is the elapsed-time tick; later entries are one-shot timeouts.
    const current: Resources = {
      queue: [], startedAt: performance.now(), timers: [0], finishing: false, settled: false,
    };
    resources.current = current;
    setPhase("connecting");
    try {
      // Create the audio context inside the tap's user gesture; Safari keeps a
      // context created after an await suspended, which records silence.
      const context = new AudioContext();
      current.context = context;
      current.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      if (current.settled) return;
      const session = await dictationApi.createSession();
      current.session = session;
      if (current.settled) return;
      setMaxSeconds(session.max_seconds);

      const protocol = createProtocol(session, {
        onText: (delta) => callbacks.current.onText(delta),
        onDone: () => release({ cancelled: false }),
        onError: (message) => release({ cancelled: false, error: message }),
      });
      current.protocol = protocol;

      await context.resume();
      await context.audioWorklet.addModule(pcmWorkletUrl());
      if (current.settled) return;
      const node = new AudioWorkletNode(context, "pwc-pcm-capture", {
        processorOptions: { targetRate: session.sample_rate },
      });
      current.node = node;
      const mute = context.createGain();
      mute.gain.value = 0;
      context.createMediaStreamSource(current.stream).connect(node).connect(mute).connect(context.destination);

      const socket = new WebSocket(socketUrl(session.ws_url));
      current.socket = socket;
      const send = (message: string) => {
        if (socket.readyState === WebSocket.OPEN) socket.send(message);
        else current.queue.push(message);
      };
      node.port.onmessage = (event: MessageEvent<{ pcm?: ArrayBuffer; level?: number; flushed?: boolean }>) => {
        if (typeof event.data.level === "number") setLevel(event.data.level);
        if (event.data.pcm && event.data.pcm.byteLength) send(protocol.audio(toBase64(event.data.pcm)));
        if (event.data.flushed) protocol.finish().forEach(send);
      };
      const tick = () => {
        if (current.settled || current.finishing) return;
        const seconds = (performance.now() - current.startedAt) / 1000;
        setElapsed(seconds);
        if (seconds >= session.max_seconds) finish();
        else current.timers[0] = window.setTimeout(tick, 250);
      };
      // Recording (and the session clock) starts once the relay accepts the
      // socket; audio captured before then is queued, not lost.
      socket.onopen = () => {
        protocol.open().forEach((message) => socket.send(message));
        current.queue.splice(0).forEach((message) => socket.send(message));
        if (current.settled || current.finishing) return;
        current.startedAt = performance.now();
        setPhase("recording");
        tick();
      };
      socket.onmessage = (event) => {
        if (typeof event.data === "string") protocol.receive(event.data);
      };
      socket.onclose = (event) => {
        if (current.settled) return;
        release({ cancelled: false, error: event.code === 1000 ? undefined : "Voice input disconnected." });
      };
      current.stream.getTracks()[0]?.addEventListener("ended", () => {
        if (resources.current === current) finish();
      });
    } catch (error) {
      release({ cancelled: false, error: dictationErrorMessage(error) });
    }
  }, [finish, release]);

  React.useEffect(() => () => release({ cancelled: true }, true), [release]);

  return { phase, elapsed, maxSeconds, level, start, finish, cancel };
}
