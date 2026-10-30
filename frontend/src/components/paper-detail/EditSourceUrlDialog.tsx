import { useState } from "react";
import { Input } from "@/components/ui/input";
import { papersApi } from "@/lib/api/papers";
import { PaperEditDialogShell } from "./PaperEditDialogShell";
import { usePaperSectionEdit, type PaperSectionEditorProps } from "./usePaperSectionEdit";

interface EditSourceUrlDialogProps extends PaperSectionEditorProps {
  initialUrl: string;
}

export function EditSourceUrlDialog({
  onOpenChange,
  paperId,
  arxivId,
  initialUrl,
  submitMode = "direct",
  isAuthor = false,
}: EditSourceUrlDialogProps) {
  const [editedUrl, setEditedUrl] = useState(initialUrl);
  const save = usePaperSectionEdit({
    editType: "source_url",
    paperId,
    arxivId,
    submitMode,
    messages: {
      proposal: "source URL change",
      noun: "source URL",
      failure: "Failed to update source URL.",
    },
    toPendingPayload: (sourceUrl: string) => ({ source_url: sourceUrl }),
    applyDirect: (sourceUrl) => papersApi.updateSourceUrl(paperId, sourceUrl),
    onClose: () => onOpenChange(false),
  });

  const trimmed = editedUrl.trim();
  const isValidUrl = /^https?:\/\//i.test(trimmed);
  const hasChange = trimmed !== (initialUrl || "").trim();

  const handleSave = () => {
    if (!isValidUrl) return;
    save.mutate(trimmed);
  };

  return (
    <PaperEditDialogShell
      title="Edit Source URL"
      description='Update the canonical URL for this external paper. This is the page the "Source page" button links to. ArXiv papers cannot edit this field.'
      className="max-w-2xl"
      submitMode={submitMode}
      isAuthor={isAuthor}
      onOpenChange={onOpenChange}
      onSave={handleSave}
      isSaving={save.isPending}
      saveDisabled={!isValidUrl || !hasChange}
    >
      <div className="space-y-2 py-2">
        <label className="text-sm font-medium">Source URL</label>
        <Input
          type="url"
          placeholder="https://example.com/paper"
          value={editedUrl}
          onChange={(e) => setEditedUrl(e.target.value)}
          onKeyPress={(e) => {
            if (e.key === "Enter" && isValidUrl && hasChange) {
              e.preventDefault();
              handleSave();
            }
          }}
        />
        {!isValidUrl && trimmed.length > 0 && (
          <p className="text-xs text-destructive">
            URL must start with http:// or https://
          </p>
        )}
      </div>
    </PaperEditDialogShell>
  );
}
