import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AWAITING_MARKDOWN_MESSAGE,
  codexApi,
  type CodexPaperJob,
  type CodexPaperJobKind,
} from "@/lib/api/codex";
import { adminQueryKeys } from "@/lib/api/queryKeys";

const JOB_COPY = {
  "add-evals": {
    trigger: "add evals",
    running: "adding evals…",
    complete: "add evals ✓",
    title: "Add evaluations with Codex",
    description: (paperTitle: string) => (
      <>
        Codex will run the repository’s add-evals skill for “{paperTitle}”. It will import only
        paper-native results onto existing, metric-compatible leaderboards. Accepted rows are
        written directly to the live database.
      </>
    ),
    notice:
      "Comparator rows, unknown benchmarks, and unconfigured metrics will be skipped. Jobs run one at a time in submission order.",
    progress:
      "Codex is researching the paper and validating results against the configured leaderboards.",
    action: "Run add-evals",
  },
  "enrich-paper": {
    trigger: "enrich paper",
    running: "enriching…",
    complete: "enriched ✓",
    title: "Enrich paper with Codex",
    description: (paperTitle: string) => (
      <>
        Codex will run the repository’s enrich-paper skill for “{paperTitle}”. It will validate
        official code and project links, merge high-confidence taxonomy tags, and check the paper
        thumbnail. Accepted changes are written directly to the live database.
      </>
    ),
    notice:
      "Uncertain URLs and missing taxonomy concepts will be reported rather than guessed. Jobs run one at a time in submission order.",
    progress: "Codex is validating artifacts, taxonomy tags, and thumbnail quality for this paper.",
    action: "Run enrich-paper",
  },
} as const;

const ACTIVE_STATUSES = new Set<CodexPaperJob["status"]>([
  "queued",
  "dispatching",
  "running",
  "awaiting_markdown",
]);

interface CodexPaperJobDialogProps {
  kind: CodexPaperJobKind;
  paperId: number;
  paperTitle: string;
  triggerClassName: string;
  onComplete: () => void;
}

function CodexJobReport({ report }: { report: string }) {
  return (
    <div className="min-w-0 max-h-[50vh] overflow-y-auto overflow-x-hidden rounded-md border bg-muted/40 p-4 text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, ...props }) => (
            <a
              {...props}
              className="break-all underline underline-offset-2"
              target="_blank"
              rel="noreferrer"
            >
              {children}
            </a>
          ),
          p: ({ children }) => <p className="mb-3 break-words last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
          ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
          h1: ({ children }) => <h3 className="mb-2 font-semibold">{children}</h3>,
          h2: ({ children }) => <h3 className="mb-2 font-semibold">{children}</h3>,
          h3: ({ children }) => <h3 className="mb-2 font-semibold">{children}</h3>,
          code: ({ children }) => (
            <code className="break-all rounded bg-background/80 px-1 py-0.5 font-mono text-xs">
              {children}
            </code>
          ),
          pre: ({ children }) => (
            <pre className="mb-3 max-w-full overflow-x-auto whitespace-pre-wrap break-words rounded bg-background/80 p-3 font-mono text-xs last:mb-0">
              {children}
            </pre>
          ),
        }}
      >
        {report}
      </ReactMarkdown>
    </div>
  );
}

export function CodexPaperJobDialog({
  kind,
  paperId,
  paperTitle,
  triggerClassName,
  onComplete,
}: CodexPaperJobDialogProps) {
  const copy = JOB_COPY[kind];
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const completedJobId = useRef<string | null>(null);

  const jobQuery = useQuery({
    queryKey: adminQueryKeys.codexPaperJob(kind, jobId),
    queryFn: () => codexApi.getPaperJob(kind, jobId!),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "awaiting_markdown") return 60_000;
      return status && ACTIVE_STATUSES.has(status) ? 2_000 : false;
    },
    retry: false,
  });
  const showJob = (next: CodexPaperJob) => {
    queryClient.setQueryData(adminQueryKeys.codexPaperJob(kind, next.id), next);
    setJobId(next.id);
  };
  const start = useMutation({
    mutationFn: () => codexApi.startPaperJob(kind, paperId),
    onSuccess: showJob,
  });
  const cancel = useMutation({
    mutationFn: (id: string) => codexApi.cancelPaperJob(kind, id),
    onSuccess: showJob,
  });

  const job = jobId ? jobQuery.data : undefined;
  const waiting = job?.status === "awaiting_markdown";
  const active = job ? ACTIVE_STATUSES.has(job.status) : false;
  // A job written by start/cancel supersedes an earlier failed poll.
  const pollError = jobQuery.errorUpdatedAt > jobQuery.dataUpdatedAt ? jobQuery.error : null;
  const error = (start.error ?? cancel.error ?? pollError)?.message;

  useEffect(() => {
    if (job?.status !== "completed" || completedJobId.current === job.id) return;
    completedJobId.current = job.id;
    onComplete();
  }, [job, onComplete]);

  const reset = () => {
    setJobId(null);
    start.reset();
    cancel.reset();
    completedJobId.current = null;
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <button type="button" className={triggerClassName} onClick={() => setOpen(true)}>
        {waiting ? "waiting for Markdown…" : active ? copy.running : job?.status === "completed" ? copy.complete : copy.trigger}
      </button>
      <DialogContent className="max-h-[90vh] w-[calc(100vw-2rem)] min-w-0 max-w-2xl overflow-hidden">
        <DialogHeader className="min-w-0">
          <DialogTitle>{copy.title}</DialogTitle>
          <DialogDescription>{copy.description(paperTitle)}</DialogDescription>
        </DialogHeader>

        {!job ? (
          <div className="rounded-md border bg-muted/40 p-3 text-sm text-muted-foreground">
            {copy.notice}
          </div>
        ) : (
          <div className="min-w-0 space-y-3 overflow-hidden">
            <div className="font-mono text-xs uppercase tracking-wide text-muted-foreground">
              Status: {job.status.replace("_", " ")}
            </div>
            {job.hf_job_url && (
              <a className="text-sm underline" href={job.hf_job_url} target="_blank" rel="noreferrer">
                View Hugging Face Job
              </a>
            )}
            {waiting && (
              <div className="rounded-md border bg-muted/40 p-3 text-sm">
                {AWAITING_MARKDOWN_MESSAGE} You can close this window and return.
              </div>
            )}
            {active && !waiting && (
              <div className="rounded-md border bg-muted/40 p-3 text-sm">
                {job.status === "queued"
                  ? "This job is queued and will start after the current Codex job finishes."
                  : copy.progress}{" "}
                This can take several minutes; you can close this window and return.
              </div>
            )}
            {job.report && <CodexJobReport report={job.report} />}
            {job.error && !waiting && (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                {job.error}
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            {active ? "Close" : "Cancel"}
          </Button>
          {active && job && <Button variant="outline" onClick={() => cancel.mutate(job.id)}>Cancel job</Button>}
          {!job && (
            <Button onClick={() => start.mutate()} disabled={start.isPending}>
              {start.isPending ? "Starting…" : copy.action}
            </Button>
          )}
          {job && !active && (
            <Button variant="outline" onClick={reset}>
              Run again
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
