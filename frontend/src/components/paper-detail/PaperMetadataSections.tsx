import { useState } from "react";

import { MethodChip, TagChip } from "@/components";
import { LatexText } from "@/components/LatexTitle";
import type { Paper } from "@/lib/api/papers.types";

import { PaperSectionRule } from "./PaperSectionRule";
import { PaperSuggestedQuestions } from "./PaperSuggestedQuestions";

const ABSTRACT_PREVIEW_LENGTH = 360;

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
  const [abstractExpanded, setAbstractExpanded] = useState(false);
  const abstract = paper.abstract || "";
  const isLongAbstract = abstract.length > ABSTRACT_PREVIEW_LENGTH;
  const abstractView = abstractExpanded || !isLongAbstract
    ? abstract
    : `${abstract.slice(0, ABSTRACT_PREVIEW_LENGTH)}…`;

  return (
    <>
      {paper.tldr && (
        <>
          <PaperSectionRule id="tldr" label="TL;DR" />
          <div className="tldr-box">{paper.tldr}</div>
        </>
      )}
      <PaperSuggestedQuestions paper={paper} readerChatRoute={readerChatRoute} />

      <PaperSectionRule id="abstract" label="Abstract" />
      <p className="abstract-text" style={{ marginBottom: 8 }}>
        <LatexText text={abstractView} />
      </p>
      {isLongAbstract && (
        <button
          type="button"
          className="read-full"
          onClick={() => setAbstractExpanded((expanded) => !expanded)}
        >
          {abstractExpanded ? "− collapse abstract" : "+ read full abstract"}
        </button>
      )}

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
