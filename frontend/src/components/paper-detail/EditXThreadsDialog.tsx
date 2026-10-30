import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { papersApi } from "@/lib/api/papers";
import { PaperEditDialogShell } from "./PaperEditDialogShell";
import { usePaperSectionEdit, type PaperSectionEditorProps } from "./usePaperSectionEdit";

const MAX_X_THREADS = 10;
// Mirrors backend/services/x_thread_service.py so typos are caught before saving.
const X_POST_URL =
  /^https?:\/\/(?:www\.|mobile\.)?(?:x|twitter)\.com\/(?:[A-Za-z0-9_]{1,15}|i\/web|i)\/status(?:es)?\/(\d{1,25})(?:[/?#].*)?$/;

function postId(url: string): string | null {
  return X_POST_URL.exec(url.trim())?.[1] ?? null;
}

interface EditXThreadsDialogProps extends PaperSectionEditorProps {
  initialUrls: string[];
}

export function EditXThreadsDialog({
  onOpenChange,
  paperId,
  arxivId,
  initialUrls,
  submitMode = "direct",
  isAuthor = false,
}: EditXThreadsDialogProps) {
  const [urls, setUrls] = useState<string[]>(initialUrls);
  const [newUrl, setNewUrl] = useState("");
  const [inputError, setInputError] = useState<string | null>(null);
  const save = usePaperSectionEdit({
    editType: "x_threads",
    paperId,
    arxivId,
    submitMode,
    messages: {
      proposal: "X threads",
      noun: "X threads",
      failure: "Failed to update X threads.",
    },
    toPendingPayload: (next: string[]) => ({ x_threads: next }),
    applyDirect: (next) => papersApi.updateXThreads(paperId, next),
    onClose: () => onOpenChange(false),
  });

  // Folds the typed-but-not-added URL into the list; null means it is invalid.
  const withTypedUrl = (): string[] | null => {
    const trimmed = newUrl.trim();
    if (!trimmed) return urls;
    const id = postId(trimmed);
    if (!id) {
      setInputError("Paste a post URL such as https://x.com/user/status/123…");
      return null;
    }
    if (urls.some((url) => postId(url) === id)) {
      setInputError("This post is already listed.");
      return null;
    }
    if (urls.length >= MAX_X_THREADS) {
      setInputError(`A paper can link at most ${MAX_X_THREADS} X threads.`);
      return null;
    }
    return [...urls, trimmed];
  };

  const handleAdd = () => {
    const next = withTypedUrl();
    if (next === null) return;
    setUrls(next);
    setNewUrl("");
    setInputError(null);
  };

  const move = (index: number, offset: number) => {
    const next = [...urls];
    [next[index], next[index + offset]] = [next[index + offset], next[index]];
    setUrls(next);
  };

  const handleSave = () => {
    const next = withTypedUrl();
    if (next === null) return;
    if (
      submitMode === "direct" &&
      initialUrls.some((url) => !next.some((candidate) => postId(candidate) === postId(url))) &&
      !window.confirm("Remove one or more X threads from this paper?")
    ) return;
    save.mutate(next);
  };

  const hasChange = useMemo(() => {
    const candidate = newUrl.trim() ? [...urls, newUrl.trim()] : urls;
    return candidate.map(postId).join() !== initialUrls.map(postId).join();
  }, [urls, newUrl, initialUrls]);

  return (
    <PaperEditDialogShell
      title="Edit X threads"
      description="Link posts on X (formerly Twitter) in which the authors introduce this paper. A preview of each post is shown on the paper page."
      className="max-w-2xl max-h-[600px]"
      submitMode={submitMode}
      isAuthor={isAuthor}
      onOpenChange={onOpenChange}
      onSave={handleSave}
      isSaving={save.isPending}
      saveDisabled={!hasChange}
    >
      <div className="space-y-2">
        <label className="text-sm font-medium" htmlFor="x-thread-url">Add X post URL</label>
        <div className="flex space-x-2">
          <Input
            id="x-thread-url"
            type="url"
            placeholder="https://x.com/user/status/1234567890"
            value={newUrl}
            onChange={(event) => {
              setNewUrl(event.target.value);
              setInputError(null);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                handleAdd();
              }
            }}
            aria-invalid={Boolean(inputError)}
            className="flex-1"
          />
          <Button onClick={handleAdd} size="sm" disabled={!newUrl.trim()}>
            <Plus className="w-4 h-4 mr-1" />
            Add
          </Button>
        </div>
        {inputError && <p className="text-xs text-destructive">{inputError}</p>}
      </div>

      <div className="py-4 overflow-y-auto max-h-[350px]">
        {urls.length > 0 ? (
          <div className="space-y-2">
            {urls.map((url, index) => (
              <div key={url} className="flex items-center space-x-2 p-3 bg-muted/30 rounded-lg">
                <span className="flex-1 min-w-0 truncate text-sm font-medium">{url}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 px-2"
                  disabled={index === 0}
                  onClick={() => move(index, -1)}
                  aria-label="Move up"
                >
                  <ArrowUp className="w-4 h-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 px-2"
                  disabled={index === urls.length - 1}
                  onClick={() => move(index, 1)}
                  aria-label="Move down"
                >
                  <ArrowDown className="w-4 h-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 px-2 text-destructive hover:text-destructive"
                  onClick={() => setUrls(urls.filter((candidate) => candidate !== url))}
                  aria-label="Remove X thread"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-center py-8 text-sm text-muted-foreground">No X threads linked yet</p>
        )}
      </div>
    </PaperEditDialogShell>
  );
}
