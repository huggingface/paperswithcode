import { Link } from "react-router-dom";

import LatexTitle from "@/components/LatexTitle";
import type { RelatedPaperRecommendation } from "@/lib/api/papers.types";

export function RelatedPapersCard({
  isLoading,
  papers,
}: {
  isLoading: boolean;
  papers?: RelatedPaperRecommendation[];
}) {
  if (isLoading) {
    return (
      <div className="sidebar-card" aria-busy="true">
        <h2 className="sidebar-card-title">Related papers</h2>
        <div className="related-meta">Finding related work…</div>
      </div>
    );
  }
  if (!papers?.length) return null;

  return (
    <div className="sidebar-card">
      <h2 className="sidebar-card-title">Related papers</h2>
      {papers.map((paper) => (
        <Link
          key={paper.id}
          to={`/paper/${paper.arxiv_id || paper.id}`}
          target="_blank"
          rel="noopener noreferrer"
          className="related-paper"
          style={{ textDecoration: "none", color: "inherit" }}
        >
          <div className="related-title">
            <LatexTitle title={paper.title} />
          </div>
          <div className="related-meta">
            <span>{paper.arxiv_id ? `arXiv:${paper.arxiv_id}` : "External resource"}</span>
            {paper.citation_count != null && (
              <span>{paper.citation_count.toLocaleString()} cites</span>
            )}
          </div>
        </Link>
      ))}
    </div>
  );
}
