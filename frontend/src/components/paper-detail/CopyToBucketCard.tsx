import { useEffect, useMemo, useState } from "react";

import { Icon } from "@/components/Icon";
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
import { useToast } from "@/hooks/use-toast";
import {
  buildBucketCopyCommands,
  clearPendingBucketAuthorization,
  collectBucketArtifacts,
  huggingFaceBucketUrl,
  loadPendingBucketAuthorization,
  type BucketArtifactKind,
  type BucketArtifactSources,
  type BucketDestination,
  type BucketVisibility,
} from "@/lib/bucketCopy";
import { safeExternalHref } from "@/lib/safeExternalHref";
import { useBucketCopy } from "./useBucketCopy";

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

export function CopyToBucketCard(props: CopyToBucketCardProps) {
  const { toast } = useToast();
  const { githubUrls, hfDatasetUrls, hfModelUrls, hfSpaceUrls, paperId, pdfName, pdfUrl } = props;
  const artifacts = useMemo(
    () => collectBucketArtifacts({ githubUrls, hfDatasetUrls, hfModelUrls, hfSpaceUrls, paperId, pdfName, pdfUrl }),
    [githubUrls, hfDatasetUrls, hfModelUrls, hfSpaceUrls, paperId, pdfName, pdfUrl],
  );
  // Returning from the bucket-authorization sign-in restores the dialog and resumes the copy.
  const pendingAuthorization = useMemo(() => loadPendingBucketAuthorization(paperId), [paperId]);
  const [open, setOpen] = useState(Boolean(pendingAuthorization));
  const [destinationMode, setDestinationMode] = useState<BucketDestination>(
    pendingAuthorization?.destinationMode ?? "new",
  );
  const [bucketId, setBucketId] = useState(pendingAuthorization?.bucketId ?? "");
  const [visibility, setVisibility] = useState<BucketVisibility>(pendingAuthorization?.visibility ?? "public");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(pendingAuthorization?.selectedIds ?? artifacts.map((artifact) => artifact.id)),
  );
  const [resumeAfterAuthorization, setResumeAfterAuthorization] = useState(Boolean(pendingAuthorization));

  const selectedArtifacts = artifacts.filter((artifact) => selectedIds.has(artifact.id));
  const allArtifactsSelected = selectedArtifacts.length === artifacts.length;
  const bucketPageUrl = huggingFaceBucketUrl(bucketId);
  const bucketIdIsValid = bucketPageUrl !== null;
  const commands = buildBucketCopyCommands(bucketId, selectedArtifacts, {
    create: destinationMode === "new",
    isPrivate: visibility === "private",
  });
  const { copy: copyNow, copying, progress: copyProgress } = useBucketCopy({
    paperId,
    isSignedIn: props.isSignedIn,
    bucketId,
    destinationMode,
    visibility,
    selected: selectedArtifacts,
    onDone: () => setOpen(false),
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

  useEffect(() => {
    if (!resumeAfterAuthorization || !props.isSignedIn) return;
    setResumeAfterAuthorization(false);
    clearPendingBucketAuthorization(paperId);
    void copyNow();
  }, [copyNow, props.isSignedIn, paperId, resumeAfterAuthorization]);

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
