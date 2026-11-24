import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { refreshPaperQueries } from "@/lib/api/cacheSync";
import { papersApi } from "@/lib/api/papers";
import { getApiErrorMessage } from "@/lib/apiTransport";
import { PaperEditDialogShell } from "./PaperEditDialogShell";
import type { PaperSectionEditorProps } from "./usePaperSectionEdit";

const MAX_LENGTH = 50;
const SUGGESTIONS = ["Technical Report", "System Card", "Model Card", "White Paper"];

interface EditDocumentTypeDialogProps extends PaperSectionEditorProps {
  initialType: string;
}

/** Admin-only editor for the document type used in a paper page's search title. */
export function EditDocumentTypeDialog({
  onOpenChange,
  paperId,
  arxivId,
  initialType,
}: EditDocumentTypeDialogProps) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [value, setValue] = useState(initialType);
  const normalized = value.split(/\s+/).filter(Boolean).join(" ");
  const hasChange = normalized !== initialType.trim();
  const tooLong = normalized.length > MAX_LENGTH;

  const save = useMutation({
    mutationFn: () => papersApi.updateDocumentType(paperId, normalized || null),
    onSuccess: (paper) => {
      refreshPaperQueries(queryClient, paper, [paperId, arxivId]);
      onOpenChange(false);
    },
    onError: (error) => {
      toast({
        title: "Could not save document type",
        description: getApiErrorMessage(error, "Failed to update document type."),
        variant: "destructive",
      });
    },
  });

  const canSave = hasChange && !tooLong && !save.isPending;
  const handleSave = () => {
    if (canSave) save.mutate();
  };

  return (
    <PaperEditDialogShell
      title="Edit Document Type"
      description="Set what kind of document this is, such as a technical report. It appears in the page's search title. Leave it empty for an ordinary paper."
      className="max-w-lg"
      submitMode="direct"
      onOpenChange={onOpenChange}
      onSave={handleSave}
      isSaving={save.isPending}
      saveDisabled={!hasChange || tooLong}
    >
      <div className="space-y-2 py-2">
        <label className="text-sm font-medium" htmlFor="paper-document-type">
          Document type
        </label>
        <Input
          id="paper-document-type"
          placeholder="Technical Report"
          value={value}
          list="paper-document-type-suggestions"
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              handleSave();
            }
          }}
        />
        <datalist id="paper-document-type-suggestions">
          {SUGGESTIONS.map((suggestion) => (
            <option key={suggestion} value={suggestion} />
          ))}
        </datalist>
        {tooLong && (
          <p className="text-xs text-destructive">
            Use at most {MAX_LENGTH} characters.
          </p>
        )}
      </div>
    </PaperEditDialogShell>
  );
}
