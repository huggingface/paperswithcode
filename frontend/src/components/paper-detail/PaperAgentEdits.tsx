import { useState } from "react";
import { Check, Copy, History } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { paperEditsApi } from "@/lib/api/paperEdits";

export function PaperAgentEdits({ paperId }: { paperId: number }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const [open, setOpen] = useState(() => window.location.hash.startsWith("#edit"));
  const history = useInfiniteQuery({ queryKey: ["paper-edit-history", paperId], queryFn: ({ pageParam }) => paperEditsApi.history(paperId, pageParam), initialPageParam: undefined as string | undefined, getNextPageParam: page => page.next_cursor ?? undefined, enabled: open });
  const prompt = `Help me edit https://paperswithcode.co/paper/${paperId} using the public pwc CLI from https://github.com/huggingface/pwc-cli. Install or update the CLI following its README, then run pwc skills add to load its instructions. Run pwc auth login --paper ${paperId}; I will authorize this paper in my browser. Export with pwc paper edit export ${paperId} --output edits.json, make explicit operations for the corrections I request, and preview before submitting. For organization changes, use an organizations operation with payload {"organization_ids": [existing organization IDs]}; this replaces the paper’s organization links and publishes directly. Use existing organizations, benchmark and metric definitions, preserve unrelated entries, and cite source URLs where available. Never print or copy credentials. Ask me what to change if I have not specified it.`;
  return <>
    <button type="button" className="action-btn" title="Copy a prompt to edit this paper with your coding agent" onClick={async () => {
      try { await navigator.clipboard.writeText(prompt); setCopied(true); setCopyError(false); }
      catch { setCopyError(true); }
    }}>{copied ? <Check size={12} /> : <Copy size={12} />}{copied ? "Prompt copied" : "Edit with your agent"}</button>
    <button type="button" className="action-btn" onClick={() => setOpen(true)}><History size={12} /> View edit history</button>
    <Dialog open={copyError} onOpenChange={setCopyError}>
      <DialogContent>
        <DialogHeader><DialogTitle>Copy the edit prompt</DialogTitle><DialogDescription>Paste these instructions into your coding agent.</DialogDescription></DialogHeader>
        <textarea aria-label="Paper edit prompt" readOnly value={prompt} className="h-64 w-full rounded border p-3 text-sm" onFocus={event => event.currentTarget.select()} />
      </DialogContent>
    </Dialog>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto" id="edit-history">
        <DialogHeader><DialogTitle>Paper edit history</DialogTitle><DialogDescription>Published changes and their contributors.</DialogDescription></DialogHeader>
        <div className="space-y-3">
      {history.isLoading && <p>Loading edit history…</p>}
      {history.error && <p role="alert">Could not load edit history.</p>}
      {history.data && !history.data.pages[0].events.length && <p className="text-sm text-muted-foreground">No edits have been recorded here yet.</p>}
      {history.data?.pages.flatMap(page => page.events).map(event => <article key={event.id} id={`edit-${event.id}`} className="rounded border p-3">
        <p className="text-sm">{event.actor_username ? <a className="underline" href={`https://huggingface.co/${encodeURIComponent(event.actor_username)}`}>@{event.actor_username}</a> : "Catalog administrator"} · {new Date(event.created_at).toLocaleString()} · {event.operation === "rollback" ? "Reverted an edit" : "Updated this paper"}</p>
        <details><summary className="cursor-pointer text-sm">View changes</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify({ before: event.before, after: event.after }, null, 2)}</pre></details>
      </article>)}
      {history.hasNextPage && <Button variant="outline" disabled={history.isFetchingNextPage} onClick={() => void history.fetchNextPage()}>Load older edits</Button>}
        </div>
      </DialogContent>
    </Dialog>
  </>;
}
