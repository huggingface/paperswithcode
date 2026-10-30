import { useCallback, useRef } from "react";

import { hfLoginUrl } from "@/lib/apiUrl";
import { chatApi } from "@/lib/api/chat";
import type { ChatDraft, ReasoningEffort } from "@/lib/chat";
import {
  chatAuthorizationAttempted,
  keepChatDraftForRetry,
  queueAuthorizedChatSend,
} from "@/lib/chatLaunch";

interface InferenceAuthorizationOptions {
  /** Where the browser returns after Hugging Face sign-in. */
  returnTo: () => string;
  selectedModel: string;
  reasoningEffort: ReasoningEffort;
  userBilledInference: boolean;
  /** Hand an unsent prompt back to the composer with an explanation. */
  onPromptRestored: (draft: ChatDraft, message: string) => void;
}

/**
 * Hugging Face sign-in and Inference Providers authorization before a send.
 * The prompt survives the redirect and is sent once on return.
 */
export function useInferenceAuthorization({
  returnTo,
  selectedModel,
  reasoningEffort,
  userBilledInference,
  onPromptRestored,
}: InferenceAuthorizationOptions) {
  const connectedRef = useRef(false);
  const checkPendingRef = useRef(false);

  const authorize = useCallback((draft: ChatDraft) => {
    queueAuthorizedChatSend(draft, selectedModel, reasoningEffort);
    window.location.href = hfLoginUrl(returnTo(), { authorizeInference: userBilledInference });
  }, [reasoningEffort, returnTo, selectedModel, userBilledInference]);

  const restorePrompt = useCallback((draft: ChatDraft, message: string) => {
    keepChatDraftForRetry(draft, selectedModel);
    onPromptRestored(draft, message);
  }, [onPromptRestored, selectedModel]);

  const checkBilling = useCallback(async (draft: ChatDraft): Promise<boolean> => {
    if (checkPendingRef.current) return false;
    checkPendingRef.current = true;
    try {
      const billing = await chatApi.getInferenceBilling();
      if (!billing.connected) {
        if (chatAuthorizationAttempted()) {
          restorePrompt(
            draft,
            "Hugging Face inference authorization was not completed. Your prompt is ready to retry.",
          );
          return false;
        }
        authorize(draft);
        return false;
      }
      connectedRef.current = true;
      return true;
    } catch (error) {
      restorePrompt(
        draft,
        error instanceof Error
          ? error.message
          : "Could not check Hugging Face authorization.",
      );
      return false;
    } finally {
      checkPendingRef.current = false;
    }
  }, [authorize, restorePrompt]);

  /** True when the draft may be sent now. Otherwise the browser is redirecting
   * to sign-in or the prompt was restored. Synchronous when no check is needed. */
  const authorizeSend = useCallback((draft: ChatDraft, signedIn: boolean): boolean | Promise<boolean> => {
    if (!signedIn) {
      authorize(draft);
      return false;
    }
    if (userBilledInference && !connectedRef.current) return checkBilling(draft);
    return true;
  }, [authorize, checkBilling, userBilledInference]);

  return { authorizeSend, restorePrompt };
}
