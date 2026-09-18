import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { paperPreviewQueryKey } from "@/components/paper-preview/paperPreviewCache";
import { papersApi } from "@/lib/api/papers";
import { useOptionalAuth } from "@/lib/authContext";

export const ARXIV_ROUTE_ID = /^(\d{4}\.\d{4,5}|[a-z-]+(\.[A-Z]{2})?\/\d{7})$/i;

// Shown in a preview card when the catalog has no row for a cited arXiv paper.
// Signed-in readers submit in place and the card reloads once the paper is
// indexed; everyone else lands on the submit page with the ID prefilled.
export const PaperIndexRequest: React.FC<{ arxivId: string }> = ({ arxivId }) => {
  const auth = useOptionalAuth();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => papersApi.submit({ arxiv_id: arxivId }),
    onSuccess: (data) => {
      if (!data.pending_review) void queryClient.invalidateQueries({ queryKey: paperPreviewQueryKey(arxivId) });
    },
  });
  if (mutation.data?.pending_review) {
    return (
      <div className="paper-preview-status paper-preview-index-request">
        <span>Indexing request queued for review.</span>
        <Link to="/submissions" target="_blank" rel="noopener noreferrer">View submissions ↗</Link>
      </div>
    );
  }
  return (
    <div className="paper-preview-status paper-preview-index-request">
      <span>Not indexed on Papers with Code yet.</span>
      {auth?.user ? (
        <button type="button" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
          {mutation.isPending ? "Requesting…" : "Request indexing"}
        </button>
      ) : (
        <Link to={`/submit?arxiv_id=${encodeURIComponent(arxivId)}`} target="_blank" rel="noopener noreferrer">
          Request indexing ↗
        </Link>
      )}
      {mutation.isError && <span role="alert">{mutation.error.message}</span>}
    </div>
  );
};
