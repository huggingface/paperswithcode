import { DEFAULT_REASONING_EFFORT, type ChatDraft, type ChatStreamRequest, type ReasoningEffort } from "@/lib/chat";
import { toPaperSelectionWire } from "@/lib/paperSelection";

/** Per-chat settings every stream request carries. */
export interface ChatRequestContext {
  webSearchEnabled?: boolean;
  reasoningEffort?: ReasoningEffort;
  primaryPaperRouteId?: string;
  viewerContext?: () => { page: number } | undefined;
}

type RequestTarget = Pick<ChatStreamRequest, "session_id" | "client_message_id"> & Partial<ChatStreamRequest>;

/** One stream request: its target fields plus the chat's settings. */
export function buildChatRequest(
  context: ChatRequestContext,
  message: string,
  target: RequestTarget,
): ChatStreamRequest {
  return {
    message,
    ...target,
    web_search_enabled: Boolean(context.webSearchEnabled),
    reasoning_effort: context.reasoningEffort ?? DEFAULT_REASONING_EFFORT,
  };
}

export function primaryPaperField(context: ChatRequestContext): Partial<ChatStreamRequest> {
  return context.primaryPaperRouteId ? { primary_paper_route_id: context.primaryPaperRouteId } : {};
}

/** A new or edited prompt's content and reader context. */
export function draftRequestFields(context: ChatRequestContext, draft: ChatDraft): Partial<ChatStreamRequest> {
  const viewerContext = context.viewerContext?.();
  return {
    paper_mentions: draft.paperMentions.map(({ route_id, title, start, end }) => ({ route_id, title, start, end })),
    ...primaryPaperField(context),
    ...(viewerContext ? { viewer_context: viewerContext } : {}),
    ...(draft.paperSelection ? { paper_selection: toPaperSelectionWire(draft.paperSelection) } : {}),
  };
}
