import { useState } from "react";

import { MethodChip, TagChip } from "@/components/Chips";
import { LatexText } from "@/components/LatexTitle";
import type { Paper } from "@/lib/api/papers.types";

import { AbstractText } from "./AbstractText";

import { PaperSectionRule } from "./PaperSectionRule";
import { PaperSuggestedQuestions } from "./PaperSuggestedQuestions";

export function PaperMetadataSections({
  canEdit,
  onEditMethods,
  onEditTasks,
  paper,
  readerChatRoute,
}: {
  canEdit: boolean;
  onEditMethods: () => void;
  onEditTasks: () => void;
  paper: Paper;
  readerChatRoute: string | null;
}) {
  const abstract = paper.abstract || "";
  // Deep links to #tldr open the summary they point at.
  const [tldrOpen] = useState(() => window.location.hash === "#tldr");

  return (
    <>
      <PaperSectionRule id="abstract" label="Abstract" />
      <p className="abstract-text">
        {paper.abstract_mentions?.length ? (
          <AbstractText abstract={abstract} mentions={paper.abstract_mentions} />
        ) : (
          <LatexText text={abstract} />
        )}
      </p>
      {paper.tldr && (
        <details className="tldr-details paper-section-anchor" id="tldr" open={tldrOpen}>
          <summary>
            <span className="tldr-toggle-show">Show TL;DR</span>
            <span className="tldr-toggle-hide">Hide TL;DR</span>
            <span className="tldr-toggle-hint">short summary</span>
          </summary>
          <div className="tldr-box">{paper.tldr}</div>
        </details>
      )}
      <PaperSuggestedQuestions paper={paper} readerChatRoute={readerChatRoute} />

      <PaperSectionRule
        id="tasks"
        label="Tasks"
        accent={
          <span className="accent">
            {paper.tasks?.length || 0} tagged
            {canEdit && (
              <button type="button" onClick={onEditTasks} className="edit-link">edit</button>
            )}
          </span>
        }
      />
      <div className="paper-tags" style={{ marginBottom: 8 }}>
        {(paper.tasks ?? []).map((task) => (
          <TagChip key={task.id} slug={task.slug || ""} label={task.name} />
        ))}
      </div>

      <PaperSectionRule
        id="methods"
        label="Methods"
        accent={
          <span className="accent">
            {paper.methods?.length || 0} used
            {canEdit && (
              <button type="button" onClick={onEditMethods} className="edit-link">edit</button>
            )}
          </span>
        }
      />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
        {(paper.methods ?? []).map((method) => (
          <MethodChip key={method.id} method={method} />
        ))}
      </div>
    </>
  );
}
