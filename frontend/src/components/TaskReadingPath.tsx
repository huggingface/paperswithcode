import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { catalogQueries } from "@/lib/api/queries";

interface TaskReadingPathProps {
  taskId: string;
  label: string;
}

/** Sidebar "Start here" path: overview, foundations, recent work. Renders
 *  nothing while loading, on error, or when the task has no path. */
export default function TaskReadingPath({ taskId, label }: TaskReadingPathProps) {
  const { data } = useQuery(catalogQueries.taskReadingPath(taskId));
  if (!data?.steps.length) return null;

  return (
    <div className="side-block task-reading-path" aria-labelledby="task-reading-path-label">
      <div className="side-block-num">{label}</div>
      <div className="side-block-label" id="task-reading-path-label">
        Start here
        <span className="task-reading-path-source">
          {data.source === "curated" ? "curated" : "auto-picked"}
        </span>
      </div>
      <ol className="task-reading-path-steps">
        {data.steps.map((step, index) => (
          <li key={step.kind} className="task-reading-path-step">
            <div className="task-reading-path-step-title" title={step.description}>
              {index + 1}. {step.title}
            </div>
            {step.papers.map(({ paper, note }) => (
              <Link
                key={paper.id}
                to={`/paper/${paper.arxiv_id || paper.id}`}
                className="task-reading-path-paper"
                title={note ?? undefined}
              >
                <span>{paper.title}</span>
                {paper.published && (
                  <span className="count">{paper.published.slice(0, 4)}</span>
                )}
              </Link>
            ))}
          </li>
        ))}
      </ol>
    </div>
  );
}
