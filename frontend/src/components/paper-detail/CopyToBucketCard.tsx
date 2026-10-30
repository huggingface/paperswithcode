import { useCallback, useEffect, useMemo, useState } from "react";

import { Icon } from "@/components";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { ToastAction } from "@/components/ui/toast";
import { useToast } from "@/hooks/use-toast";
import { ApiError } from "@/lib/apiTransport";
import { papersApi } from "@/lib/api/papers";
import { hfLoginUrl } from "@/lib/apiUrl";
import { safeExternalHref } from "@/lib/safeExternalHref";

type BucketArtifactKind = "pdf" | "model" | "dataset" | "space" | "github";

export interface BucketArtifact {
  id: string;
  kind: BucketArtifactKind;
  label: string;
  url: string;
  source: string;
  destination: string;
  repoId?: string;
}

interface BucketArtifactSources {
  githubUrls: string[];
  hfModelUrls: string[];
  hfDatasetUrls: string[];
  hfSpaceUrls: string[];
  paperId: string;
  pdfName: string;
  pdfUrl?: string | null;
}

interface CopyToBucketCardProps extends BucketArtifactSources {
  isSignedIn: boolean;
  suggestedBucketId?: string;
}

const KIND_LABEL: Record<BucketArtifactKind, string> = {
  pdf: "PDF",
  model: "Model",
  dataset: "Dataset",
  space: "Space",
  github: "GitHub",
};
const REPO_PART_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const BUCKET_ID_RE = /^[A-Za-z0-9][\w.-]*\/[A-Za-z0-9][\w.-]*$/;
const DIRECT_COPY_BATCH_SIZE = 20;

export interface DirectBucketArtifact {
  kind: "model" | "dataset" | "space";
  repo_id: string;
}

interface PendingBucketAuthorization {
  paperId: string;
  bucketId: string;
  destinationMode: "new" | "existing";
  visibility: "public" | "private";
  selectedIds: string[];
}

const BUCKET_AUTHORIZATION_PARAM = "copy_to_bucket";

function huggingFaceBucketUrl(bucketId: string): string | null {
  const normalized = bucketId.trim();
  if (!BUCKET_ID_RE.test(normalized)) return null;
  const [namespace, name] = normalized.split("/");
  return `https://huggingface.co/buckets/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}`;
}

function pendingBucketAuthorizationKey(paperId: string): string {
  return `pwc:bucket-copy:${paperId}`;
}

function loadPendingBucketAuthorization(paperId: string): PendingBucketAuthorization | null {
  if (typeof window === "undefined") return null;
  const url = new URL(window.location.href);
  if (url.searchParams.get(BUCKET_AUTHORIZATION_PARAM) !== paperId) return null;

  try {
    const raw = window.sessionStorage.getItem(pendingBucketAuthorizationKey(paperId));
    if (!raw) return null;
    const pending = JSON.parse(raw) as PendingBucketAuthorization;
    if (
      pending.paperId !== paperId ||
      typeof pending.bucketId !== "string" ||
      !["new", "existing"].includes(pending.destinationMode) ||
      !["public", "private"].includes(pending.visibility) ||
      !Array.isArray(pending.selectedIds) ||
      pending.selectedIds.some((id) => typeof id !== "string")
    ) {
      return null;
    }
    return pending;
  } catch {
    return null;
  }
}

export function chunkBucketArtifacts(
  artifacts: DirectBucketArtifact[],
  batchSize = DIRECT_COPY_BATCH_SIZE,
): DirectBucketArtifact[][] {
  if (batchSize < 1) throw new Error("Bucket copy batch size must be positive");

  const batches: DirectBucketArtifact[][] = [];
  for (let start = 0; start < artifacts.length; start += batchSize) {
    batches.push(artifacts.slice(start, start + batchSize));
  }
  return batches;
}

function shellQuote(value: string): string {
  return "'" + value.replace(/'/g, "'\"'\"'") + "'";
}

function parseHfArtifact(
  url: string,
  kind: Exclude<BucketArtifactKind, "github" | "pdf">,
): BucketArtifact | null {
  try {
    const parsed = new URL(url);
    if (parsed.hostname !== "huggingface.co") return null;

    const parts = parsed.pathname.split("/").filter(Boolean);
    const prefix = kind === "model" ? [] : [`${kind}s`];
    if (prefix.length && parts[0] !== prefix[0]) return null;
    const repoParts = parts.slice(prefix.length, prefix.length + 2);
    if (repoParts.length !== 2 || repoParts.some((part) => !REPO_PART_RE.test(part))) return null;

    const repoId = repoParts.join("/");
    const sourcePrefix = kind === "model" ? "" : `${kind}s/`;
    return {
      id: `${kind}:${repoId}`,
      kind,
      label: repoId,
      url: `https://huggingface.co/${sourcePrefix}${repoId}`,
      source: `hf://${sourcePrefix}${repoId}/`,
      destination: `${kind}s/${repoId}/`,
      repoId,
    };
  } catch {
    return null;
  }
}

function parseGithubArtifact(url: string): BucketArtifact | null {
  try {
    const parsed = new URL(url);
    if (parsed.hostname !== "github.com" && parsed.hostname !== "www.github.com") return null;
    const parts = parsed.pathname.split("/").filter(Boolean);
    if (parts.length < 2) return null;

    const owner = parts[0];
    const repo = parts[1].replace(/\.git$/, "");
    if (!REPO_PART_RE.test(owner) || !REPO_PART_RE.test(repo)) return null;
    const repoId = `${owner}/${repo}`;
    return {
      id: `github:${repoId}`,
      kind: "github",
      label: repoId,
      url: `https://github.com/${repoId}`,
      source: `https://github.com/${repoId}.git`,
      destination: `github/${repoId}/`,
    };
  } catch {
    return null;
  }
}

export function collectBucketArtifacts({
  githubUrls,
  hfModelUrls,
  hfDatasetUrls,
  hfSpaceUrls,
  paperId,
  pdfName,
  pdfUrl,
}: BucketArtifactSources): BucketArtifact[] {
  const candidates = [
    pdfUrl
      ? {
          id: "pdf",
          kind: "pdf" as const,
          label: "Paper PDF",
          url: pdfUrl,
          source: pdfUrl,
          destination: `paper/${pdfName || paperId}.pdf`,
        }
      : null,
    ...hfModelUrls.map((url) => parseHfArtifact(url, "model")),
    ...hfDatasetUrls.map((url) => parseHfArtifact(url, "dataset")),
    ...hfSpaceUrls.map((url) => parseHfArtifact(url, "space")),
    ...githubUrls.map(parseGithubArtifact),
  ];
  const seen = new Set<string>();
  return candidates.filter((artifact): artifact is BucketArtifact => {
    if (!artifact || seen.has(artifact.id)) return false;
    seen.add(artifact.id);
    return true;
  });
}

export function buildBucketCopyCommands(
  bucketId: string,
  artifacts: BucketArtifact[],
  options: { create: boolean; isPrivate: boolean },
): string {
  const lines = [
    "# Requires the Hugging Face CLI: https://huggingface.co/docs/huggingface_hub/guides/cli",
    `HF_BUCKET=${shellQuote(bucketId.trim())}`,
  ];

  if (options.create) {
    lines.push(
      `hf buckets create "$HF_BUCKET" --exist-ok${options.isPrivate ? " --private" : ""}`,
    );
  }

  for (const artifact of artifacts.filter(
    (item) => item.kind !== "github" && item.kind !== "pdf",
  )) {
    lines.push(
      `hf cp ${shellQuote(artifact.source)} "hf://buckets/$HF_BUCKET/${artifact.destination}"`,
    );
  }

  const pdfArtifact = artifacts.find((item) => item.kind === "pdf");
  if (pdfArtifact) {
    lines.push(
      'PWC_PDF="$(mktemp)"',
      "trap 'rm -f \"$PWC_PDF\"' EXIT",
      `curl --fail --location ${shellQuote(pdfArtifact.source)} --output "$PWC_PDF"`,
      `hf cp "$PWC_PDF" "hf://buckets/$HF_BUCKET/${pdfArtifact.destination}"`,
    );
  }

  const githubArtifacts = artifacts.filter((item) => item.kind === "github");
  if (githubArtifacts.length) {
    lines.push(
      'PWC_COPY_DIR="$(mktemp -d)"',
      "trap 'rm -rf \"$PWC_COPY_DIR\"' EXIT",
    );
    for (const artifact of githubArtifacts) {
      const localPath = `$PWC_COPY_DIR/${artifact.destination.replace(/\/$/, "")}`;
      lines.push(
        `git clone --depth 1 -- ${shellQuote(artifact.source)} "${localPath}"`,
        `hf sync "${localPath}" "hf://buckets/$HF_BUCKET/${artifact.destination}" --exclude '.git/**'`,
      );
    }
  }

  return lines.join("\n");
}

export function paperArtifactBucketName(title: string): string {
  const shortTitle = title.split(/[:|–—]/, 1)[0] || title;
  const slug = shortTitle
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48)
    .replace(/-+$/g, "");
  return `${slug || "paper"}-artifacts`;
}

export function CopyToBucketCard(props: CopyToBucketCardProps) {
  const { toast } = useToast();
  const artifacts = useMemo(
    () =>
      collectBucketArtifacts({
        githubUrls: props.githubUrls,
        hfDatasetUrls: props.hfDatasetUrls,
        hfModelUrls: props.hfModelUrls,
        hfSpaceUrls: props.hfSpaceUrls,
        paperId: props.paperId,
        pdfName: props.pdfName,
        pdfUrl: props.pdfUrl,
      }),
    [
      props.githubUrls,
      props.hfDatasetUrls,
      props.hfModelUrls,
      props.hfSpaceUrls,
      props.paperId,
      props.pdfName,
      props.pdfUrl,
    ],
  );
  const pendingAuthorization = useMemo(
    () => loadPendingBucketAuthorization(props.paperId),
    [props.paperId],
  );
  const [open, setOpen] = useState(Boolean(pendingAuthorization));
  const [destinationMode, setDestinationMode] = useState<"new" | "existing">(
    pendingAuthorization?.destinationMode ?? "new",
  );
  const [bucketId, setBucketId] = useState(pendingAuthorization?.bucketId ?? "");
  const [visibility, setVisibility] = useState<"public" | "private">(
    pendingAuthorization?.visibility ?? "public",
  );
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () =>
      new Set(
        pendingAuthorization?.selectedIds ?? artifacts.map((artifact) => artifact.id),
      ),
  );
  const [copying, setCopying] = useState(false);
  const [copyProgress, setCopyProgress] = useState<{ current: number; total: number } | null>(null);
  const [resumeAfterAuthorization, setResumeAfterAuthorization] = useState(
    Boolean(pendingAuthorization),
  );

  const selectedArtifacts = artifacts.filter((artifact) => selectedIds.has(artifact.id));
  const allArtifactsSelected = selectedArtifacts.length === artifacts.length;
  const bucketPageUrl = huggingFaceBucketUrl(bucketId);
  const bucketIdIsValid = bucketPageUrl !== null;
  const commands = buildBucketCopyCommands(bucketId, selectedArtifacts, {
    create: destinationMode === "new",
    isPrivate: visibility === "private",
  });

  const toggleArtifact = (id: string, checked: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const copyCommands = async () => {
    try {
      await navigator.clipboard.writeText(commands);
      toast({
        title: "Bucket copy commands copied",
        description: "Run them in a terminal where the Hugging Face CLI is signed in.",
      });
    } catch {
      toast({
        title: "Copy failed",
        description: "Could not access the clipboard. Select and copy the commands manually.",
        variant: "destructive",
      });
    }
  };

  const authorizeBucket = useCallback(() => {
    const returnUrl = new URL(window.location.href);
    returnUrl.searchParams.set(BUCKET_AUTHORIZATION_PARAM, props.paperId);
    window.sessionStorage.setItem(
      pendingBucketAuthorizationKey(props.paperId),
      JSON.stringify({
        paperId: props.paperId,
        bucketId: bucketId.trim(),
        destinationMode,
        visibility,
        selectedIds: Array.from(selectedIds),
      } satisfies PendingBucketAuthorization),
    );
    window.location.assign(hfLoginUrl(returnUrl.toString(), {
      authorizeBucket: true,
      bucketCreate: destinationMode === "new",
    }));
  }, [bucketId, destinationMode, props.paperId, selectedIds, visibility]);

  const copyNow = useCallback(async () => {
    if (!props.isSignedIn) {
      authorizeBucket();
      return;
    }
    setCopying(true);
    let copiedCount = 0;
    let failedCount = 0;
    try {
      const directArtifacts = selectedArtifacts
        .filter(
          (artifact): artifact is BucketArtifact & {
            kind: "model" | "dataset" | "space";
            repoId: string;
          } =>
            artifact.kind !== "pdf" &&
            artifact.kind !== "github" &&
            Boolean(artifact.repoId),
        )
        .map((artifact) => ({ kind: artifact.kind, repo_id: artifact.repoId }));
      const artifactBatches = chunkBucketArtifacts(directArtifacts);
      if (!artifactBatches.length) artifactBatches.push([]);

      for (const [batchIndex, artifactBatch] of artifactBatches.entries()) {
        setCopyProgress({ current: batchIndex + 1, total: artifactBatches.length });
        const result = await papersApi.copyToBucket(props.paperId, {
          bucket_id: bucketId.trim(),
          create: batchIndex === 0 && destinationMode === "new",
          private: visibility === "private",
          include_pdf:
            batchIndex === 0 && selectedArtifacts.some((artifact) => artifact.kind === "pdf"),
          artifacts: artifactBatch,
        });
        copiedCount += result.copied.length;
        failedCount += result.errors.length;
      }

      const githubCount = selectedArtifacts.filter((artifact) => artifact.kind === "github").length;
      toast({
        title: failedCount ? "Bucket copy partially completed" : "Copied to bucket",
        description: [
          `${copiedCount} item${copiedCount === 1 ? "" : "s"} copied.`,
          failedCount ? `${failedCount} item${failedCount === 1 ? "" : "s"} failed.` : "",
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
      if (!failedCount && !githubCount) setOpen(false);
    } catch (error) {
      if (error instanceof ApiError && error.code === "bucket_authorization_required") {
        authorizeBucket();
        return;
      }
      toast({
        title: copiedCount ? "Bucket copy partially completed" : "Bucket copy failed",
        description: copiedCount
          ? `${copiedCount} item${copiedCount === 1 ? "" : "s"} copied before the request failed. You can retry or use the CLI commands below.`
          : error instanceof ApiError && typeof error.detail === "string"
            ? error.detail
            : "Hugging Face could not complete the copy. You can still use the CLI commands below.",
        variant: "destructive",
      });
    } finally {
      setCopying(false);
      setCopyProgress(null);
    }
  }, [
    authorizeBucket,
    bucketId,
    bucketPageUrl,
    destinationMode,
    props.isSignedIn,
    props.paperId,
    selectedArtifacts,
    toast,
    visibility,
  ]);

  useEffect(() => {
    if (!resumeAfterAuthorization || !props.isSignedIn) return;

    setResumeAfterAuthorization(false);
    window.sessionStorage.removeItem(pendingBucketAuthorizationKey(props.paperId));
    const url = new URL(window.location.href);
    url.searchParams.delete(BUCKET_AUTHORIZATION_PARAM);
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
    void copyNow();
  }, [copyNow, props.isSignedIn, props.paperId, resumeAfterAuthorization]);

  const openDialog = () => {
    setSelectedIds(new Set(artifacts.map((artifact) => artifact.id)));
    if (!bucketId && props.suggestedBucketId) {
      setBucketId(props.suggestedBucketId);
    }
    setOpen(true);
  };

  return (
    <>
      <div className="sidebar-card copy-to-bucket-card">
        <button
          type="button"
          className="copy-to-bucket-trigger"
          onClick={openDialog}
        >
          <span className="copy-to-bucket-arrow" aria-hidden="true">→</span>
          <span className="copy-to-bucket-title">Copy to bucket</span>
          <span className="copy-to-bucket-new">New</span>
        </button>
        <div className="copy-to-bucket-meta">
          {artifacts.length
            ? `${artifacts.length} linked artifact${artifacts.length === 1 ? "" : "s"}`
            : "No linked artifacts yet"}
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] max-w-2xl grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <span className="copy-to-bucket-dialog-arrow" aria-hidden="true">→</span>
              Copy to bucket
            </DialogTitle>
            <DialogDescription>
              Keep your own copy of this paper&apos;s PDF, linked code, and Hugging
              Face artifacts. Hub repositories use Xet&apos;s server-side copy;
              GitHub repositories use the generated CLI fallback.
            </DialogDescription>
          </DialogHeader>

          <div className="-mx-6 min-h-0 overflow-y-auto px-6">
            {artifacts.length ? (
              <div className="space-y-5">
              <div className="space-y-2">
                <Label>Choose your destination</Label>
                <RadioGroup
                  value={destinationMode}
                  onValueChange={(value) => setDestinationMode(value as "new" | "existing")}
                  className="grid grid-cols-2 gap-2"
                >
                  <Label className="bucket-choice">
                    <RadioGroupItem value="new" />
                    New bucket
                  </Label>
                  <Label className="bucket-choice">
                    <RadioGroupItem value="existing" />
                    Existing bucket
                  </Label>
                </RadioGroup>
              </div>

              <div className="space-y-2">
                <Label htmlFor="bucket-id">Bucket name</Label>
                <Input
                  id="bucket-id"
                  value={bucketId}
                  onChange={(event) => setBucketId(event.target.value)}
                  placeholder={props.suggestedBucketId || "username/paper-artifacts"}
                  aria-invalid={bucketId.length > 0 && !bucketIdIsValid}
                />
                <div className="flex items-center justify-between gap-3 text-xs">
                  <p className="text-muted-foreground">
                    Use the full Hugging Face bucket ID: namespace/name.
                  </p>
                  {bucketPageUrl && (
                    <a
                      href={bucketPageUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex shrink-0 items-center gap-1 underline underline-offset-4"
                    >
                      View bucket
                      <Icon name="external" size={10} />
                    </a>
                  )}
                </div>
              </div>

              {destinationMode === "new" && (
                <div className="space-y-2">
                  <Label>Bucket visibility</Label>
                  <RadioGroup
                    value={visibility}
                    onValueChange={(value) => setVisibility(value as "public" | "private")}
                    className="flex gap-5"
                  >
                    <Label className="flex items-center gap-2 font-normal">
                      <RadioGroupItem value="public" />
                      Public
                    </Label>
                    <Label className="flex items-center gap-2 font-normal">
                      <RadioGroupItem value="private" />
                      Private
                    </Label>
                  </RadioGroup>
                </div>
              )}

              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <Label>Artifacts</Label>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() =>
                      setSelectedIds(
                        allArtifactsSelected
                          ? new Set()
                          : new Set(artifacts.map((artifact) => artifact.id)),
                      )
                    }
                  >
                    {allArtifactsSelected ? "Deselect all" : "Select all"}
                  </Button>
                </div>
                <div className="bucket-artifact-list">
                  {artifacts.map((artifact) => (
                    <div key={artifact.id} className="bucket-artifact-row">
                      <Checkbox
                        id={`bucket-artifact-${artifact.id}`}
                        checked={selectedIds.has(artifact.id)}
                        onCheckedChange={(checked) => toggleArtifact(artifact.id, checked === true)}
                      />
                      <Label
                        htmlFor={`bucket-artifact-${artifact.id}`}
                        className="min-w-0 flex-1 cursor-pointer font-normal"
                      >
                        <span className="bucket-artifact-kind">{KIND_LABEL[artifact.kind]}</span>
                        <span className="bucket-artifact-name">{artifact.label}</span>
                      </Label>
                      <a
                        href={safeExternalHref(artifact.url) ?? undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="bucket-artifact-open"
                      >
                        Open
                        <Icon name="external" size={10} />
                      </a>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  The PDF and Hugging Face artifacts can be copied directly.
                  GitHub repositories require the CLI workflow below.
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="bucket-copy-commands">CLI fallback</Label>
                <pre
                  id="bucket-copy-commands"
                  className="bucket-copy-commands h-[190px]"
                >
                  {bucketIdIsValid
                    ? commands
                    : "Enter a bucket name above to prepare the copy commands."}
                </pre>
              </div>
              </div>
            ) : (
              <p className="py-5 text-sm text-muted-foreground">
                This paper does not have a linked GitHub repository or Hugging Face
                artifact to copy yet.
              </p>
            )}
          </div>

          <DialogFooter>
            <a
              href="https://huggingface.co/docs/huggingface_hub/en/guides/buckets"
              target="_blank"
              rel="noopener noreferrer"
              className="mr-auto text-sm text-muted-foreground underline underline-offset-4"
            >
              About Hugging Face Buckets
            </a>
            <Button
              type="button"
              onClick={copyCommands}
              variant="outline"
              disabled={!bucketIdIsValid || selectedArtifacts.length === 0}
            >
              <Icon name="copy" size={12} />
              Copy commands
            </Button>
            <Button
              type="button"
              onClick={copyNow}
              disabled={
                copying ||
                (props.isSignedIn &&
                  (!bucketIdIsValid ||
                    !selectedArtifacts.some((artifact) => artifact.kind !== "github")))
              }
            >
              {copying
                ? copyProgress && copyProgress.total > 1
                  ? `Copying ${copyProgress.current}/${copyProgress.total}…`
                  : "Copying…"
                : props.isSignedIn
                  ? "Copy now"
                  : "Sign in & copy"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
