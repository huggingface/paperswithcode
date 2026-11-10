import type { ApiRequest } from "../apiTransport";
import { apiRequest } from "./request";

export type DictationProvider = "voxtral" | "openai";

export interface DictationStatus {
  enabled: boolean;
  signed_in: boolean;
  provider: DictationProvider | null;
  /** Why no provider can take a session: "starting", "busy" or "daily_limit". */
  reason: string | null;
  max_seconds: number;
  remaining_seconds: number | null;
}

export interface DictationSession {
  session_id: string;
  /** Same-origin WebSocket path carrying a single-use ticket. */
  ws_url: string;
  provider: DictationProvider;
  model: string;
  sample_rate: number;
  max_seconds: number;
  prompt: string | null;
}

export class DictationApi {
  constructor(private readonly request: ApiRequest) {}

  /** Also wakes the scale-to-zero speech endpoint for signed-in users. */
  getStatus(): Promise<DictationStatus> {
    return this.request("/dictation/status", { cache: "no-store" });
  }

  createSession(): Promise<DictationSession> {
    return this.request("/dictation/sessions", { method: "POST", cache: "no-store" });
  }

  /** Settles the session at its recorded length; survives page unloads. */
  finishSession(sessionId: string, seconds: number): Promise<void> {
    return this.request(`/dictation/sessions/${encodeURIComponent(sessionId)}/finish`, {
      method: "POST",
      body: JSON.stringify({ seconds }),
      keepalive: true,
    });
  }
}

export const dictationApi = new DictationApi(apiRequest);
