import { apiUrl } from "@/lib/apiUrl";
import type { ChatBlock, ChatMessage } from "@/lib/chat";

export interface ChatSession {
  id: string;
  title: string;
  selected_model: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  is_busy: boolean;
}

export interface ChatSessionDetail extends ChatSession {
  transcript_status: string;
  messages: Array<{
    id: string;
    turn_id: string;
    sequence: number;
    role: "user" | "assistant";
    content: string;
    revision: number;
    status: string;
    display_blocks: ChatBlock[];
    citations: Array<{ route_id: string; title: string; source_url: string | null }>;
    followups: string[];
    error_code: string | null;
  }>;
}

export interface ChatModelChoice { id: string; label: string }

export const DEFAULT_CHAT_MODEL = "deepseek-ai/DeepSeek-V4-Flash";
export const FALLBACK_CHAT_MODELS: ChatModelChoice[] = [
  { id: DEFAULT_CHAT_MODEL, label: "DeepSeek V4 Flash" },
  { id: "zai-org/GLM-5.2", label: "GLM 5.2" },
];

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    throw new Error(detail?.message || detail || `Chat request failed (${response.status})`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export async function listSessions(): Promise<ChatSession[]> {
  const sessions: ChatSession[] = [];
  let cursor: string | null = null;
  do {
    const query = new URLSearchParams({ limit: "50" });
    if (cursor) query.set("cursor", cursor);
    const page = await request<{ items: ChatSession[]; next_cursor: string | null }>(
      `/api/v1/chat/sessions?${query.toString()}`,
    );
    sessions.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor && sessions.length < 100);
  return sessions;
}

export function getSession(id: string): Promise<ChatSessionDetail> {
  return request(`/api/v1/chat/sessions/${id}`);
}

export function updateSession(id: string, patch: { title?: string; selected_model?: string }): Promise<ChatSession> {
  return request(`/api/v1/chat/sessions/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
}

export function removeSession(id: string): Promise<void> {
  return request(`/api/v1/chat/sessions/${id}`, { method: "DELETE" });
}

export async function getChatModels(): Promise<{ items: ChatModelChoice[]; default_model: string }> {
  return request("/api/v1/chat/models");
}

export function toUiMessages(detail: ChatSessionDetail): ChatMessage[] {
  const restoreBlocks = (blocks: ChatBlock[]): ChatBlock[] => blocks.map((block) => block.kind === "reasoning"
    ? { ...block, active: false, open: false }
    : block.kind === "tool"
      ? {
          ...block,
          status: block.status === "running" ? "error" as const : block.status,
          open: block.status === "error" || block.status === "denied" || block.status === "running",
        }
      : { ...block, done: true as const });
  const failureMessage = (code: string | null): string => {
    if (code === "provider_error") return "The model provider failed before completing the response. You can edit and retry your question.";
    if (code === "persistence_error") return "The response could not be saved. You can edit and retry your question.";
    if (code === "transcript_mirror_error") return "The conversation could not be saved. Please try again in a new chat.";
    return "The response did not complete. You can edit and retry your question.";
  };

  return detail.messages.flatMap((message): ChatMessage[] => {
    if (message.role === "assistant") {
      return [{
        id: message.id,
        role: "assistant",
        blocks: restoreBlocks(message.display_blocks),
        followups: message.followups,
        citations: message.citations,
        streaming: false,
      }];
    }
    const userMessage: ChatMessage = {
      id: message.id,
      role: "user",
      text: message.content,
      revision: message.revision,
      status: message.status,
      error: message.status === "complete" ? undefined : message.error_code || message.status,
    };
    if (message.status !== "error") return [userMessage];
    return [userMessage, {
      id: `${message.id}-error`,
      role: "assistant",
      blocks: restoreBlocks(message.display_blocks),
      streaming: false,
      error: failureMessage(message.error_code),
    }];
  });
}

export interface ChatSessionGroup { label: string; items: ChatSession[] }

export function groupSessions(sessions: ChatSession[]): ChatSessionGroup[] {
  const now = Date.now();
  const startOfToday = new Date().setHours(0, 0, 0, 0);
  const groups: ChatSessionGroup[] = [
    { label: "Today", items: [] },
    { label: "Previous 7 Days", items: [] },
    { label: "Previous 30 Days", items: [] },
    { label: "Older", items: [] },
  ];
  for (const session of [...sessions].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))) {
    const timestamp = Date.parse(session.updated_at);
    const age = now - timestamp;
    if (timestamp >= startOfToday) groups[0].items.push(session);
    else if (age < 7 * 86_400_000) groups[1].items.push(session);
    else if (age < 30 * 86_400_000) groups[2].items.push(session);
    else groups[3].items.push(session);
  }
  return groups.filter((group) => group.items.length > 0);
}
