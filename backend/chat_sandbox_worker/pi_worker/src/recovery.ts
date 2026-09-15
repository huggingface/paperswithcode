import { ANSWER_NOW } from "./policy.js";

export const EXECUTION_LIMIT_FINALIZER_PROMPT =
  `${ANSWER_NOW} Produce only the best concise final answer now.`;

export const INCOMPLETE_RESPONSE_RETRY_PROMPT =
  "Your previous response ended without a visible final answer or a valid native tool call. " +
  "Continue the user's current request now. If more evidence is required, invoke an available " +
  "tool through the native tool interface; otherwise answer directly. Do not reproduce tool-call " +
  "markup as text, mention this recovery instruction, or claim an execution limit unless a tool " +
  "explicitly reported one.";

export const INCOMPLETE_RESPONSE_FINALIZER_PROMPT =
  "Your previous response ended without a visible final answer. Produce only the best concise " +
  "final answer now using evidence already gathered. Do not request or describe additional " +
  "research, mention this recovery instruction, or invent a reason for missing evidence.";

export type RecoveryReason = "execution_limit" | "incomplete_response";
export type RecoveryOutcome =
  | "not_needed"
  | "recovered_after_retry"
  | "recovered_after_finalizer"
  | "aborted"
  | "failed";

export interface CompletionPolicy {
  toolingClosed: boolean;
  needsFinalAnswer(): boolean;
}

export interface RecoverySummary {
  reason: RecoveryReason | null;
  attempts: number;
  outcome: RecoveryOutcome;
}

interface RecoveryActions {
  prompt(value: string): Promise<void>;
  disableTools(): void;
  canContinue(): boolean;
}

export async function recoverIncompleteResponse(
  policy: CompletionPolicy,
  actions: RecoveryActions,
): Promise<RecoverySummary> {
  if (!policy.needsFinalAnswer()) {
    return { reason: null, attempts: 0, outcome: "not_needed" };
  }
  const reason: RecoveryReason = policy.toolingClosed
    ? "execution_limit"
    : "incomplete_response";
  if (!actions.canContinue()) {
    return { reason, attempts: 0, outcome: "aborted" };
  }

  let attempts = 0;
  if (!policy.toolingClosed) {
    attempts += 1;
    await actions.prompt(INCOMPLETE_RESPONSE_RETRY_PROMPT);
    if (!actions.canContinue()) {
      return { reason, attempts, outcome: "aborted" };
    }
    if (!policy.needsFinalAnswer()) {
      return { reason, attempts, outcome: "recovered_after_retry" };
    }
  }

  actions.disableTools();
  attempts += 1;
  await actions.prompt(
    policy.toolingClosed
      ? EXECUTION_LIMIT_FINALIZER_PROMPT
      : INCOMPLETE_RESPONSE_FINALIZER_PROMPT,
  );
  if (!actions.canContinue()) {
    return { reason, attempts, outcome: "aborted" };
  }
  return {
    reason,
    attempts,
    outcome: policy.needsFinalAnswer() ? "failed" : "recovered_after_finalizer",
  };
}
