import { useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { paperEditsApi } from "@/lib/api/paperEdits";

export function PaperAgentEdits({ paperId }: { paperId: number }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const [open, setOpen] = useState(() => window.location.hash.startsWith("#edit"));
  const history = useInfiniteQuery({ queryKey: ["paper-edit-history", paperId], queryFn: ({ pageParam }) => paperEditsApi.history(paperId, pageParam), initialPageParam: undefined as string | undefined, getNextPageParam: page => page.next_cursor ?? undefined, enabled: open });
  const prompt = `Help me edit https://paperswithcode.co/paper/${paperId} using the public pwc CLI from https://github.com/huggingface/pwc-cli. Install or update the CLI following its README, then run pwc skills add to load its instructions. Run pwc auth login --paper ${paperId}; I will authorize this paper in my browser. Export with pwc paper edit export ${paperId} --output edits.json, make explicit operations for the corrections I request, and preview before submitting. Use existing benchmark and metric definitions, preserve unrelated entries, and cite source URLs where available. Never print or copy credentials. Ask me what to change if I have not specified it.`;
  return <section className="my-6 space-y-3" id="edit-history">
    <Button variant="outline" onClick={async () => {
      try { await navigator.clipboard.writeText(prompt); setCopied(true); setCopyError(false); }
      catch { setCopyError(true); }
    }}>{copied ? "Agent instructions copied" : "Edit with your agent"}</Button>
    <p className="text-sm text-muted-foreground">Copy instructions into your coding agent to submit links, tags, or multiple results together.</p>
    {copyError && <details open><summary>Copy these instructions</summary><p className="whitespace-pre-wrap text-sm">{prompt}</p></details>}
    <button type="button" className="text-sm underline" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Hide edit history" : "View edit history"}</button>
    {open && <div className="space-y-3">
      {history.isLoading && <p>Loading edit history…</p>}
      {history.error && <p role="alert">Could not load edit history.</p>}
      {history.data && !history.data.pages[0].events.length && <p className="text-sm text-muted-foreground">No edits have been recorded here yet.</p>}
      {history.data?.pages.flatMap(page => page.events).map(event => <article key={event.id} id={`edit-${event.id}`} className="rounded border p-3">
        <p className="text-sm">{event.actor_username ? <a className="underline" href={`https://huggingface.co/${encodeURIComponent(event.actor_username)}`}>@{event.actor_username}</a> : "Catalog administrator"} · {new Date(event.created_at).toLocaleString()} · {event.operation === "rollback" ? "Reverted an edit" : "Updated this paper"}</p>
        <details><summary className="cursor-pointer text-sm">View changes</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify({ before: event.before, after: event.after }, null, 2)}</pre></details>
      </article>)}
      {history.hasNextPage && <Button variant="outline" disabled={history.isFetchingNextPage} onClick={() => void history.fetchNextPage()}>Load older edits</Button>}
    </div>}
  </section>;
}
