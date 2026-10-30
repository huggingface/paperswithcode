import type React from "react";
import { Check, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PendingEditNotice } from "./PendingEditNotice";
import type { SubmitMode } from "./usePaperSectionEdit";

interface PaperEditDialogShellProps {
  title: string;
  description: React.ReactNode;
  className?: string;
  submitMode: SubmitMode;
  isAuthor?: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: () => void;
  isSaving: boolean;
  saveDisabled?: boolean;
  /** Footer actions shown before Cancel, such as taxonomy suggestions. */
  footerStart?: React.ReactNode;
  children: React.ReactNode;
}

/** Title, review notice and Cancel/Save footer shared by the paper section editors. */
export function PaperEditDialogShell({
  title,
  description,
  className,
  submitMode,
  isAuthor = false,
  onOpenChange,
  onSave,
  isSaving,
  saveDisabled = false,
  footerStart,
  children,
}: PaperEditDialogShellProps) {
  const pending = submitMode === "pending";
  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className={className}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {pending && <PendingEditNotice isAuthor={isAuthor} />}
        {children}
        <DialogFooter>
          {footerStart}
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={onSave} disabled={isSaving || saveDisabled}>
            {isSaving ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                {pending ? "Submitting..." : "Saving..."}
              </>
            ) : (
              <>
                <Check className="w-4 h-4 mr-2" />
                {pending ? "Submit for review" : "Save Changes"}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
