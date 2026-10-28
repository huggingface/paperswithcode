/**
 * Public paper submission page (`/submit`).
 *
 * Inspired by huggingface.co/papers/submit. Accepts either an ArXiv ID/URL
 * (routed through the existing ArXiv indexing flow) or an external paper
 * URL (delegated to `ExternalResourceService.add_from_url` on the backend,
 * which performs AI-assisted metadata extraction with optional overrides).
 * No `comment` field, per the product spec.
 */

import React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import type { PaperSubmitPayload, PaperSubmitResponse } from "@/lib/api/papers.types";
import { papersApi } from "@/lib/api/papers";
import { authUrl } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";

const SUBMIT_DRAFT_KEY = "pwc:paper-submit-draft";

// Site links inherit text color with no underline; make intro links visible.
const INLINE_LINK_STYLE: React.CSSProperties = {
  color: "var(--accent-text)",
  fontWeight: 600,
  textDecoration: "underline",
  textUnderlineOffset: 2,
};

const ARXIV_BARE_ID = /^\d{4}\.\d{4,5}(v\d+)?$/i;
const ARXIV_LEGACY_ID = /^[a-z-]+(\.[A-Z]{2})?\/\d{7}$/;
const ARXIV_URL_HOST = /^https?:\/\/(?:www\.)?arxiv\.org\//i;

type SubmissionKind = "arxiv" | "external" | "empty";

function classifyInput(raw: string): SubmissionKind {
  const value = raw.trim();
  if (!value) return "empty";
  if (ARXIV_BARE_ID.test(value) || ARXIV_LEGACY_ID.test(value)) return "arxiv";
  if (ARXIV_URL_HOST.test(value)) return "arxiv";
  if (/^https?:\/\//i.test(value)) return "external";
  // Anything else (e.g. partial input) is treated as an in-progress ArXiv ID
  return "arxiv";
}

function buildPayload(
  primary: string,
  overrides: {
    title: string;
    abstract: string;
    authors: string;
    datePublished: string;
  },
): PaperSubmitPayload {
  const value = primary.trim();
  const kind = classifyInput(value);

  if (kind === "arxiv") {
    if (/^https?:\/\//i.test(value)) {
      return { source_url: value };
    }
    return { arxiv_id: value };
  }

  const payload: PaperSubmitPayload = { source_url: value };
  const trimmedTitle = overrides.title.trim();
  if (trimmedTitle) payload.title = trimmedTitle;
  const trimmedAbstract = overrides.abstract.trim();
  if (trimmedAbstract) payload.abstract = trimmedAbstract;
  const authors = overrides.authors
    .split(/[,\n]/)
    .map((name) => name.trim())
    .filter(Boolean);
  if (authors.length > 0) payload.authors = authors;
  if (overrides.datePublished) payload.date_published = overrides.datePublished;
  return payload;
}

function extractErrorDetail(err: unknown): string {
  const e = err as { response?: string; message?: string } | undefined;
  if (!e) return "Submission failed";
  if (e.response) {
    try {
      const parsed = JSON.parse(e.response);
      if (typeof parsed.detail === "string") return parsed.detail;
      if (parsed.detail?.message) {
        return `${parsed.detail.message} See ${parsed.detail.help || "/rate-limits"} for help.`;
      }
    } catch {
      return e.response;
    }
  }
  return e.message || "Submission failed";
}

const SubmitView: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { user, isLoading: authLoading } = useAuth();

  // Preview cards link here with the citation's arXiv ID prefilled.
  const [searchParams] = useSearchParams();
  const prefilledArxivId = searchParams.get("arxiv_id") ?? "";
  const [input, setInput] = React.useState(prefilledArxivId);
  const [title, setTitle] = React.useState("");
  const [abstract, setAbstract] = React.useState("");
  const [authors, setAuthors] = React.useState("");
  const [datePublished, setDatePublished] = React.useState("");
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null);

  React.useEffect(() => {
    // A prefilled citation wins over an older draft, which stays stored for
    // the next plain visit.
    if (prefilledArxivId) return;
    const raw = sessionStorage.getItem(SUBMIT_DRAFT_KEY);
    if (!raw) return;
    sessionStorage.removeItem(SUBMIT_DRAFT_KEY);
    try {
      const draft = JSON.parse(raw) as Record<string, string>;
      setInput(draft.input ?? "");
      setTitle(draft.title ?? "");
      setAbstract(draft.abstract ?? "");
      setAuthors(draft.authors ?? "");
      setDatePublished(draft.datePublished ?? "");
    } catch {
      // Ignore a corrupt browser-local draft.
    }
  }, [prefilledArxivId]);

  const kind = classifyInput(input);
  const isExternal = kind === "external";

  const mutation = useMutation<PaperSubmitResponse, Error, PaperSubmitPayload>({
    mutationFn: (payload) => papersApi.submit(payload),
    onSuccess: (data) => {
      if (data.pending_review) {
        toast({
          title: "Submission queued for review",
          description: "No source page was fetched and no catalog row was changed.",
        });
        mutation.reset();
        return;
      }
      queryClient.invalidateQueries({ queryKey: ["papers"], refetchType: "none" });
      queryClient.invalidateQueries({
        queryKey: ["papers-infinite"],
        refetchType: "none",
      });
      queryClient.invalidateQueries({
        queryKey: ["trending-papers"],
        refetchType: "none",
      });
      const importedNewVersion = data.refreshed && data.created && data.latest_version;
      toast({
        title: importedNewVersion
          ? `Paper updated to ${data.latest_version}`
          : data.created
            ? "Paper submitted"
            : "Paper already indexed",
        description: importedNewVersion
          ? "Opening the updated paper page…"
          : data.created
            ? "Opening the paper page…"
            : "Opening the existing paper page…",
      });
      if (data.route_identifier) navigate(`/paper/${data.route_identifier}`);
    },
    onError: (err) => {
      setErrorMsg(extractErrorDetail(err));
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    if (kind === "empty") {
      setErrorMsg("Enter an arXiv ID or a paper URL to submit.");
      return;
    }

    if (!user) {
      sessionStorage.setItem(
        SUBMIT_DRAFT_KEY,
        JSON.stringify({ input, title, abstract, authors, datePublished }),
      );
      const login = authUrl("/api/v1/auth/hf/login");
      window.location.assign(
        `${login}?return_to=${encodeURIComponent(window.location.href)}`,
      );
      return;
    }

    const payload = buildPayload(input, {
      title,
      abstract,
      authors,
      datePublished,
    });
    mutation.mutate(payload);
  };

  return (
    <div className="page" style={{ maxWidth: 720 }}>
      <h1 className="detail-title">Submit a paper</h1>
      <p
        style={{
          fontFamily: "var(--serif)",
          color: "var(--ink-soft)",
          marginTop: 12,
          lineHeight: 1.55,
        }}
      >
        If your paper is on arXiv, submit it on{" "}
        <a
          href="https://huggingface.co/papers/submit"
          target="_blank"
          rel="noopener noreferrer"
          style={INLINE_LINK_STYLE}
        >
          Hugging Face
        </a>
        , which will automatically index it on Papers with Code.
      </p>
      <p
        style={{
          fontFamily: "var(--serif)",
          color: "var(--ink-soft)",
          marginTop: 12,
          lineHeight: 1.55,
        }}
      >
        If your paper is not on arXiv, submit it here. Non-arXiv papers (blog
        posts, technical reports, model release pages) enter the submission
        queue and appear only after review.
        {" "}
        <a href="/rate-limits" style={INLINE_LINK_STYLE}>
          Read the submission and rate-limit policy.
        </a>
      </p>

      <form
        onSubmit={handleSubmit}
        style={{ marginTop: 28, display: "grid", gap: 20 }}
      >
        <div style={{ display: "grid", gap: 8 }}>
          <label
            htmlFor="submit-input"
            style={{ fontWeight: 600, fontSize: 14 }}
          >
            arXiv ID or paper URL
          </label>
          <Input
            id="submit-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="2501.12345  ·  https://arxiv.org/abs/2501.12345  ·  https://blog.example.com/release"
            autoFocus
            required
          />
          <div
            style={{
              fontSize: 12,
              color: "var(--ink-soft)",
              minHeight: 18,
            }}
          >
            {kind === "arxiv"
              ? "Detected: arXiv paper — metadata will be fetched automatically."
              : kind === "external"
                ? "Detected: external URL — we'll extract metadata and you can override below."
                : "Paste an arXiv ID like 2501.12345 or any paper/blog URL."}
          </div>
        </div>

        {isExternal && (
          <fieldset
            style={{
              border: "1px solid var(--rule)",
              borderRadius: 8,
              padding: "16px 20px 20px",
              display: "grid",
              gap: 16,
            }}
          >
            <legend
              style={{
                padding: "0 8px",
                fontSize: 12,
                color: "var(--ink-soft)",
                textTransform: "uppercase",
                letterSpacing: 0.5,
              }}
            >
              External paper details (optional)
            </legend>

            <div style={{ display: "grid", gap: 8 }}>
              <label htmlFor="submit-title" style={{ fontSize: 13 }}>
                Title
              </label>
              <Input
                id="submit-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Leave blank to extract automatically"
              />
            </div>

            <div style={{ display: "grid", gap: 8 }}>
              <label htmlFor="submit-abstract" style={{ fontSize: 13 }}>
                Abstract or summary
              </label>
              <Textarea
                id="submit-abstract"
                value={abstract}
                onChange={(e) => setAbstract(e.target.value)}
                rows={4}
                placeholder="Leave blank to extract automatically"
              />
            </div>

            <div style={{ display: "grid", gap: 8 }}>
              <label htmlFor="submit-authors" style={{ fontSize: 13 }}>
                Authors (comma-separated)
              </label>
              <Input
                id="submit-authors"
                value={authors}
                onChange={(e) => setAuthors(e.target.value)}
                placeholder="Jane Smith, John Doe"
              />
            </div>

            <div style={{ display: "grid", gap: 8 }}>
              <label htmlFor="submit-date" style={{ fontSize: 13 }}>
                Publication date
              </label>
              <Input
                id="submit-date"
                type="date"
                value={datePublished}
                onChange={(e) => setDatePublished(e.target.value)}
                style={{ maxWidth: 220 }}
              />
              <div style={{ fontSize: 12, color: "var(--ink-soft)" }}>
                Required only if we cannot infer a date from the page.
              </div>
            </div>
          </fieldset>
        )}

        {errorMsg && (
          <Alert variant="destructive">
            <AlertDescription>{errorMsg}</AlertDescription>
          </Alert>
        )}

        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Button type="submit" disabled={mutation.isPending || authLoading}>
            {authLoading
              ? "Checking sign-in…"
              : mutation.isPending
                ? "Submitting…"
                : user
                  ? "Submit paper"
                  : "Sign in to submit"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate(-1)}
            disabled={mutation.isPending}
          >
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
};

export default SubmitView;
