/**
 * Admin-only action-row button that asks the X agent to post about this paper
 * next. Requests line up in click order at the front of the agent's queue:
 * the first one posts at the next slot, the second after it, and so on.
 * Clicking a queued paper again cancels its request.
 */

import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Icon } from "@/components/Icon";
import { operationsApi } from "@/lib/api/operations";
import { adminKeys, adminQueries } from "@/lib/api/queries";
import { getApiErrorMessage } from "@/lib/apiTransport";

interface TweetItButtonProps {
  paperId: number;
}

function ordinal(position: number): string {
  const suffix = { one: "st", two: "nd", few: "rd", other: "th" }[
    new Intl.PluralRules("en", { type: "ordinal" }).select(position) as "one" | "two" | "few" | "other"
  ];
  return `${position}${suffix}`;
}

export const TweetItButton: React.FC<TweetItButtonProps> = ({ paperId }) => {
  const queryClient = useQueryClient();
  const status = useQuery(adminQueries.xPostRequest(paperId));
  const toggle = useMutation({
    mutationFn: (requested: boolean) => operationsApi.setXPostRequest(paperId, requested),
    onSuccess: (data) => queryClient.setQueryData(adminKeys.xPostRequest(paperId), data),
  });

  const data = status.data;
  if (data?.state === "posted") {
    return data.post_url ? (
      <a className="action-btn" href={data.post_url} target="_blank" rel="noopener noreferrer">
        <Icon name="x" size={12} /> Posted on X
      </a>
    ) : (
      <button type="button" className="action-btn" disabled title="Already posted on X">
        <Icon name="x" size={12} /> Posted on X
      </button>
    );
  }

  const requested = data?.state === "requested";
  const title = requested
    ? `${ordinal(data.position ?? 1)} in line to post on X. Click to cancel.`
    : "Post about this paper on X next (admin)";
  const error = toggle.error ?? status.error;

  return (
    <>
      <button
        type="button"
        className={`action-btn${requested ? " is-saved" : ""}`}
        onClick={() => toggle.mutate(!requested)}
        disabled={!data || toggle.isPending}
        aria-pressed={requested}
        title={title}
      >
        <Icon name="x" size={12} />
        {requested ? `Queued #${data.position}` : "Tweet it"}
      </button>
      {error && (
        <span className="action-btn-error" role="alert">
          {getApiErrorMessage(error, "Could not update the X queue")}
        </span>
      )}
    </>
  );
};
