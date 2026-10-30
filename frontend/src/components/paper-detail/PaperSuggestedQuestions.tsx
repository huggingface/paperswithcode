import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Icon } from "@/components/Icon";
import { papersApi } from "@/lib/api/papers";
import type { Paper } from "@/lib/api/papers.types";
import { isChatEnabled } from "@/lib/apiUrl";
import { resetReaderSession } from "@/lib/paperReader";

/** The general chat has no paper scope, so name the paper in the prompt. */
function generalChatPrompt(paper: Paper, question: string): string {
  const reference = paper.arxiv_id ? ` (arXiv:${paper.arxiv_id.replace(/v\d+$/i, "")})` : "";
  return `About the paper "${paper.title}"${reference}: ${question}`;
}

/**
 * Three LLM-written starter questions. Each opens the paper's reader chat
 * (or the general chat when the reader has none) and asks it right away.
 */
export function PaperSuggestedQuestions({
  paper,
  readerChatRoute,
}: {
  paper: Paper;
  readerChatRoute: string | null;
}) {
  const enabled = isChatEnabled() && Boolean(paper.id && paper.abstract);
  const stored = paper.suggested_questions;
  // The detail response carries stored questions, so they render with the
  // page; only papers with none stored yet ask for them to be generated.
  const { data } = useQuery({
    queryKey: ["paper-suggested-questions", paper.id],
    queryFn: () => papersApi.suggestedQuestions(String(paper.id)),
    enabled: enabled && Array.isArray(stored) && stored.length === 0,
    // Empty means generation was skipped or failed and nothing was stored.
    staleTime: (query) => (query.state.data?.questions.length ? Infinity : 0),
    retry: false,
  });
  const questions = stored?.length ? stored : data?.questions ?? [];
  if (!enabled || questions.length === 0) return null;

  return (
    <ul className="suggested-questions" aria-label="Ask about this paper">
      {questions.map((question) => {
        const to = readerChatRoute
          ? `${readerChatRoute}?q=${encodeURIComponent(question)}`
          : `/chat?q=${encodeURIComponent(generalChatPrompt(paper, question))}`;
        return (
          <li key={question}>
            <Link
              className="suggested-question"
              to={to}
              onClick={readerChatRoute ? () => resetReaderSession(readerChatRoute) : undefined}
            >
              <Icon name="chat" size={12} />
              <span>{question}</span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
