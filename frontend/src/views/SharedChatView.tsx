import React, { useEffect, useLayoutEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import Composer from "@/components/chat/Composer";
import { ArtifactWorkspace } from "@/components/chat/ArtifactWorkspace";
import { AssistantMessage, UserMessage } from "@/components/chat/ChatMessage";
import { Spinner } from "@/components/chat/icons";
import { ArtifactPanelProvider } from "@/components/chat/useArtifactPanel";
import { isStagingEnvironment } from "@/lib/apiUrl";
import { chatApi } from "@/lib/api/chat";
import { ApiError } from "@/lib/apiTransport";
import { collectChatPapers, type ChatMessage } from "@/lib/chat";
import { queueChatLaunch } from "@/lib/chatLaunch";
import { toggleChatBlock } from "@/lib/chatLifecycle";
import { publicShareToUiMessages, type ChatShareDetail } from "@/lib/chatSessions";

const isNotFound = (error: unknown) => error instanceof ApiError && error.status === 404;

const SharedTranscript: React.FC<{ detail: ChatShareDetail }> = ({ detail }) => {
  const [messages, setMessages] = useState<ChatMessage[]>(
    () => publicShareToUiMessages(detail),
  );
  const papers = useMemo(() => collectChatPapers(messages), [messages]);
  const toggleBlock = (messageId: string, blockIndex: number) => {
    setMessages((previous) => toggleChatBlock(previous, messageId, blockIndex));
  };

  return (
    <div className="shared-chat-transcript">
      {messages.map((message) => message.role === "user"
        ? <UserMessage key={message.id} id={message.id} text={message.text ?? ""} paperMentions={message.paperMentions ?? []} paperSelection={message.paperSelection} />
        : <AssistantMessage key={message.id} msg={message} papers={papers} onToggleBlock={toggleBlock} />)}
    </div>
  );
};

const SharedChatView: React.FC = () => {
  const { shareId = "" } = useParams<{ shareId: string }>();
  const navigate = useNavigate();
  const staging = isStagingEnvironment();
  const [headerHeight, setHeaderHeight] = useState(60);
  const query = useQuery({
    queryKey: ["shared-chat", shareId],
    queryFn: () => chatApi.getSharedChat(shareId),
    retry: (count, error) => !isNotFound(error) && count < 1,
  });

  useEffect(() => {
    const previousTitle = document.title;
    const existingRobots = document.head.querySelector<HTMLMetaElement>('meta[name="robots"]');
    const previousRobots = existingRobots?.content;
    const robots = existingRobots ?? document.createElement("meta");
    robots.name = "robots";
    robots.content = "noindex,nofollow";
    if (!existingRobots) document.head.appendChild(robots);
    document.title = "Shared conversation";
    return () => {
      document.title = previousTitle;
      if (existingRobots) existingRobots.content = previousRobots ?? "";
      else robots.remove();
    };
  }, []);

  useLayoutEffect(() => {
    const header = document.querySelector<HTMLElement>(".app-header");
    if (!header) return;
    const update = () => setHeaderHeight(header.offsetHeight);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(header);
    return () => observer.disconnect();
  }, []);

  const launchFreshChat = (prompt: string) => {
    // Keep the prompt as a draft so the chat page can show access and token
    // requirements before making a request.
    queueChatLaunch(prompt, undefined, { autoSend: false });
    navigate("/chat");
  };
  const missing = isNotFound(query.error);

  if (query.isLoading) {
    return <div className="shared-chat-state" role="status"><Spinner /> Loading shared conversation…</div>;
  }
  if (missing) {
    return <div className="shared-chat-state shared-chat-not-found">
      <h1>Shared conversation not found</h1>
      <p>This link is invalid or is no longer available.</p>
    </div>;
  }
  if (query.isError || !query.data) {
    return <div className="shared-chat-state" role="alert">
      <h1>Couldn’t load this conversation</h1>
      <p>Please check your connection and try again.</p>
      <button type="button" onClick={() => void query.refetch()}>Try again</button>
    </div>;
  }

  return (
    <ArtifactPanelProvider workspaceKey={`share:${shareId}:${query.data.updated_at}`} autoOpenOnMount>
    <div className="shared-chat-page" style={{ height: `calc(100dvh - ${headerHeight}px)` }}>
      <div className="shared-chat-heading">
        <h1>Shared conversation</h1>
        {staging && <span className="chat-staging-badge">Staging</span>}
      </div>
      <ArtifactWorkspace variant="shared">
      <div className="shared-chat-content" data-testid="shared-conversation-pane">
        <SharedTranscript key={query.data.updated_at} detail={query.data} />
        {query.data.model_label && <div className="shared-chat-attribution">
          <span>Generated with {query.data.model_label}</span>
          {query.data.model_provider === "huggingface" && <span>
            Powered by <span aria-hidden="true">🤗</span>{" "}
            <a
              href="https://huggingface.co/docs/inference-providers/en/index"
              target="_blank"
              rel="noreferrer"
            >
              Inference Providers
            </a>
          </span>}
          {query.data.model_provider === "openrouter" && <span>
            Powered by <a href="https://openrouter.ai" target="_blank" rel="noreferrer">OpenRouter</a>
          </span>}
          {query.data.model_provider === "openai" && <span>Powered by OpenAI</span>}
        </div>}
        <section className="shared-chat-fresh" aria-labelledby="shared-chat-fresh-title">
          <h2 id="shared-chat-fresh-title">Start a new conversation</h2>
          <p>Your new question starts with an empty context.</p>
          {staging && <div className="shared-chat-access-note" role="note">
            <strong>Limited staging preview.</strong> Starting a chat is available only to
            approved Hugging Face users.
          </div>}
          <Composer onSend={(draft) => launchFreshChat(draft.text)} placeholder="Ask a new research question…" />
        </section>
      </div>
      </ArtifactWorkspace>
    </div>
    </ArtifactPanelProvider>
  );
};

export default SharedChatView;
