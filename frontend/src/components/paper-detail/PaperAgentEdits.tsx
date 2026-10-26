import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { AgentLogoList, AgentLogos } from "./AgentLogos";

export function PaperAgentEdits({ paperId }: { paperId: number }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const [promptOpen, setPromptOpen] = useState(false);
  const prompt = `Help me edit https://paperswithcode.co/paper/${paperId} using the public pwc CLI from https://github.com/huggingface/pwc-cli. Install or update the CLI following its README, then run pwc skills add to load its instructions. Run pwc auth login --paper ${paperId}; I will authorize this paper in my browser. Export with pwc paper edit export ${paperId} --output edits.json, make explicit operations for the corrections I request, and preview before submitting. For organization changes, use an organizations operation with payload {"organization_ids": [existing organization IDs]}; this replaces the paper’s organization links and publishes directly. Use existing organizations, benchmark and metric definitions, preserve unrelated entries, and cite source URLs where available. Never print or copy credentials. Ask me what to change if I have not specified it.`;
  return <>
    <button type="button" className="action-btn" title="Edit this paper page with Claude, Codex, Cursor, or OpenCode" onClick={() => { setCopied(false); setCopyError(false); setPromptOpen(true); }}>Edit with your agent<AgentLogos /></button>
    <Dialog open={promptOpen} onOpenChange={setPromptOpen}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Edit this paper with your agent</DialogTitle>
          <DialogDescription>Spotted a missing code link, a wrong task, or a missing benchmark result? Your favorite coding agent can fix it for you.</DialogDescription>
        </DialogHeader>
        <AgentLogoList />
        <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
          <li>Copy the prompt below.</li>
          <li>Paste it into Claude Code, Codex, Cursor, OpenCode, or another coding agent, and tell it what to change.</li>
          <li>The agent installs the <a className="underline" href="https://github.com/huggingface/pwc-cli" target="_blank" rel="noreferrer">pwc CLI</a>, asks you to authorize this paper with your Hugging Face account, and previews the edits before submitting them.</li>
        </ol>
        <textarea aria-label="Paper edit prompt" readOnly value={prompt} className="h-48 w-full resize-none rounded border bg-muted/40 p-3 font-mono text-xs" onFocus={event => event.currentTarget.select()} />
        {copyError && <p role="alert" className="text-sm text-destructive">Could not copy automatically. Select the prompt above and copy it manually.</p>}
        <Button className="justify-self-end" onClick={async () => {
          try { await navigator.clipboard.writeText(prompt); setCopied(true); setCopyError(false); }
          catch { setCopyError(true); }
        }}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? "Prompt copied" : "Copy prompt"}</Button>
      </DialogContent>
    </Dialog>
  </>;
}
