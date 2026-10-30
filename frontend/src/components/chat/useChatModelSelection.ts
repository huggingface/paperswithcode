import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { isStagingEnvironment } from "@/lib/apiUrl";
import { storedChatModel } from "@/lib/chatLaunch";
import { chatModelsQuery } from "@/lib/chatSessionQueries";
import {
  DEFAULT_CHAT_MODEL,
  PRODUCTION_FALLBACK_CHAT_MODELS,
  STAGING_FALLBACK_CHAT_MODELS,
  isSponsoredChatModel,
  providerForChatModel,
} from "@/lib/chatSessions";

interface ChatModelSelectionOptions {
  userId: string | null;
  signedIn: boolean;
  authLoading: boolean;
  /** A model asked for by the URL or a queued launch. */
  requestedModel: string | null | undefined;
  /** Saved chats keep their own model, so discovery only picks one for new chats. */
  routeSessionIdRef: { readonly current: string | undefined };
}

/** The model a chat sends with, the discovered choices, and its billing provider. */
export function useChatModelSelection({
  userId,
  signedIn,
  authLoading,
  requestedModel,
  routeSessionIdRef,
}: ChatModelSelectionOptions) {
  const requestedModelRef = useRef(requestedModel);
  const savedModelRef = useRef<string | null>(null);
  const [selectedModel, setSelectedModel] = useState(requestedModel || DEFAULT_CHAT_MODEL);
  // A model chosen after mount (picker or ?model= launch) wins over discovery's default.
  const chooseModel = useCallback((model: string) => {
    requestedModelRef.current = model;
    setSelectedModel(model);
  }, []);
  const modelsQuery = useQuery({ ...chatModelsQuery(userId), enabled: signedIn && !authLoading });
  const discovered = modelsQuery.data;
  const models = discovered?.items
    ?? (isStagingEnvironment() ? STAGING_FALLBACK_CHAT_MODELS : PRODUCTION_FALLBACK_CHAT_MODELS);

  // A model kept across authorization applies as soon as the user is known.
  useEffect(() => {
    if (authLoading || !signedIn) return;
    const savedModel = storedChatModel();
    savedModelRef.current = savedModel;
    if (savedModel) setSelectedModel(savedModel);
  }, [authLoading, signedIn]);

  useEffect(() => {
    if (!discovered || routeSessionIdRef.current) return;
    const preferred = requestedModelRef.current || savedModelRef.current;
    setSelectedModel(
      preferred && discovered.items.some((model) => model.id === preferred)
        ? preferred
        : discovered.default_model,
    );
  }, [discovered, routeSessionIdRef]);

  const provider = providerForChatModel(models, selectedModel);
  const sponsored = isSponsoredChatModel(models, selectedModel);
  return {
    models,
    selectedModel,
    setSelectedModel: chooseModel,
    provider,
    sponsored,
    /** Hugging Face models bill the user unless the organization sponsors them. */
    userBilledInference: provider === "huggingface" && !sponsored,
    lunaAvailable: models.some((model) => model.id === DEFAULT_CHAT_MODEL),
  };
}
