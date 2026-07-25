import { useState } from "react";
import { Plus } from "lucide-react";

import { SignInToEditDialog } from "@/components/paper-detail/SignInToEditDialog";
import { SuggestTaxonomyDialog } from "@/components/paper-detail/SuggestTaxonomyDialog";
import { useAuth } from "@/lib/authContext";

interface TaxonomySuggestionTileProps {
  kind: "task" | "method";
}

export function TaxonomySuggestionTile({ kind }: TaxonomySuggestionTileProps) {
  const { user } = useAuth();
  const [suggestionOpen, setSuggestionOpen] = useState(false);
  const [signInOpen, setSignInOpen] = useState(false);
  const label = `Suggest a new ${kind}...`;

  const handleClick = () => {
    if (user) {
      setSuggestionOpen(true);
    } else {
      setSignInOpen(true);
    }
  };

  return (
    <>
      <button
        type="button"
        className="tag-cell taxonomy-suggestion-cell"
        onClick={handleClick}
      >
        <div className="name">
          <Plus className="taxonomy-suggestion-icon" aria-hidden="true" />
          {label}
        </div>
        <div className="meta">
          <span>Propose an addition</span>
        </div>
      </button>
      <SuggestTaxonomyDialog
        open={suggestionOpen}
        onOpenChange={setSuggestionOpen}
        kind={kind}
      />
      <SignInToEditDialog
        open={signInOpen}
        onOpenChange={setSignInOpen}
        sectionLabel={`${kind}s`}
        returnTo={typeof window !== "undefined" ? window.location.pathname : `/${kind}s`}
        taxonomySuggestion
      />
    </>
  );
}

export default TaxonomySuggestionTile;
