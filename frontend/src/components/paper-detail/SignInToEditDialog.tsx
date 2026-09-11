/**
 * Shown when an unauthenticated visitor clicks an `edit` link on a paper page.
 *
 * Edits are open to anyone, but they require signing in with Hugging Face so
 * each submission has an account behind it. Non-admin submissions land in the
 * pending edit queue for admin review.
 */

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import HfSignInButton from "@/components/HfSignInButton";

interface SignInToEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Display name of the section the user tried to edit, e.g. "tasks". */
  sectionLabel: string;
  /** Path to return the user to after sign-in (usually the current paper URL). */
  returnTo: string;
  /** Use directory-specific copy for taxonomy suggestions. */
  taxonomySuggestion?: boolean;
}

export function SignInToEditDialog({
  open,
  onOpenChange,
  sectionLabel,
  returnTo,
  taxonomySuggestion = false,
}: SignInToEditDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            Sign in to {taxonomySuggestion ? "suggest" : "edit"} {sectionLabel}
          </DialogTitle>
          <DialogDescription>
            {taxonomySuggestion
              ? "Sign in with your Hugging Face account so an admin can review your suggestion."
              : "Anyone can suggest edits to a paper page. Sign in with your Hugging Face account first so an admin can review your submission."}
          </DialogDescription>
        </DialogHeader>
        <div className="flex justify-center pt-2">
          <HfSignInButton returnTo={returnTo} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
