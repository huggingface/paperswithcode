import { useCallback, useState } from "react";

import { ToastAction } from "@/components/ui/toast";
import { useToast } from "@/hooks/use-toast";
import { ApiError } from "@/lib/apiTransport";
import { papersApi } from "@/lib/api/papers";
import { hfLoginUrl } from "@/lib/apiUrl";
import {
  chunkBucketArtifacts,
  directBucketArtifacts,
  huggingFaceBucketUrl,
  stashBucketAuthorization,
  type BucketArtifact,
  type BucketDestination,
  type BucketVisibility,
} from "@/lib/bucketCopy";

const plural = (count: number, noun: string) => `${count} ${noun}${count === 1 ? "" : "s"}`;

interface BucketCopyRequest {
  paperId: string;
  isSignedIn: boolean;
  bucketId: string;
  destinationMode: BucketDestination;
  visibility: BucketVisibility;
  selected: BucketArtifact[];
  /** Runs after a copy that left nothing for the CLI to do. */
  onDone: () => void;
}

/**
 * The server-side copy: Hub repositories in batches, the PDF with the first
 * batch, and a sign-in round trip when the bucket needs authorizing.
 */
export function useBucketCopy({
  paperId,
  isSignedIn,
  bucketId,
  destinationMode,
  visibility,
  selected,
  onDone,
}: BucketCopyRequest) {
  const { toast } = useToast();
  const [progress, setProgress] = useState<{ current: number; total: number } | null>(null);

  const authorize = useCallback(() => {
    const returnUrl = stashBucketAuthorization({
      paperId,
      bucketId: bucketId.trim(),
      destinationMode,
      visibility,
      selectedIds: selected.map((artifact) => artifact.id),
    });
    window.location.assign(hfLoginUrl(returnUrl, {
      authorizeBucket: true,
      bucketCreate: destinationMode === "new",
    }));
  }, [bucketId, destinationMode, paperId, selected, visibility]);

  const copy = useCallback(async () => {
    if (!isSignedIn) {
      authorize();
      return;
    }
    const bucketPageUrl = huggingFaceBucketUrl(bucketId);
    setProgress({ current: 1, total: 1 });
    let copiedCount = 0;
    let failedCount = 0;
    try {
      const batches = chunkBucketArtifacts(directBucketArtifacts(selected));
      // The PDF travels with the first request, so a PDF-only copy still sends one.
      if (!batches.length) batches.push([]);

      for (const [batchIndex, batch] of batches.entries()) {
        setProgress({ current: batchIndex + 1, total: batches.length });
        const result = await papersApi.copyToBucket(paperId, {
          bucket_id: bucketId.trim(),
          create: batchIndex === 0 && destinationMode === "new",
          private: visibility === "private",
          include_pdf: batchIndex === 0 && selected.some((artifact) => artifact.kind === "pdf"),
          artifacts: batch,
        });
        copiedCount += result.copied.length;
        failedCount += result.errors.length;
      }

      const githubCount = selected.filter((artifact) => artifact.kind === "github").length;
      toast({
        title: failedCount ? "Bucket copy partially completed" : "Copied to bucket",
        description: [
          `${plural(copiedCount, "item")} copied.`,
          failedCount ? `${plural(failedCount, "item")} failed.` : "",
          githubCount ? "Use the generated commands below to copy GitHub repositories." : "",
        ].filter(Boolean).join(" "),
        variant: failedCount ? "destructive" : undefined,
        action: bucketPageUrl ? (
          <ToastAction altText="Open destination bucket" asChild>
            <a href={bucketPageUrl} target="_blank" rel="noopener noreferrer">
              Open bucket
            </a>
          </ToastAction>
        ) : undefined,
      });
      if (!failedCount && !githubCount) onDone();
    } catch (error) {
      if (error instanceof ApiError && error.code === "bucket_authorization_required") {
        authorize();
        return;
      }
      toast({
        title: copiedCount ? "Bucket copy partially completed" : "Bucket copy failed",
        description: copiedCount
          ? `${plural(copiedCount, "item")} copied before the request failed. You can retry or use the CLI commands below.`
          : error instanceof ApiError && typeof error.detail === "string"
            ? error.detail
            : "Hugging Face could not complete the copy. You can still use the CLI commands below.",
        variant: "destructive",
      });
    } finally {
      setProgress(null);
    }
  }, [authorize, bucketId, destinationMode, isSignedIn, onDone, paperId, selected, toast, visibility]);

  return { copy, copying: progress !== null, progress };
}
