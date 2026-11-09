/**
 * Copying a paper's PDF, Hub repositories and GitHub code into a Hugging Face
 * bucket: which artifacts a paper has, the direct-copy batches, the CLI
 * fallback, and the state kept across the bucket-authorization sign-in.
 */

export type BucketArtifactKind = "pdf" | "model" | "dataset" | "space" | "github";

export interface BucketArtifact {
  id: string;
  kind: BucketArtifactKind;
  label: string;
  url: string;
  source: string;
  destination: string;
  repoId?: string;
}

export interface BucketArtifactSources {
  githubUrls: string[];
  hfModelUrls: string[];
  hfDatasetUrls: string[];
  hfSpaceUrls: string[];
  paperId: string;
  pdfName: string;
  pdfUrl?: string | null;
}

/** A Hub repository the server copies with Xet's server-side copy. */
export interface DirectBucketArtifact {
  kind: "model" | "dataset" | "space";
  repo_id: string;
}

export type BucketDestination = "new" | "existing";
export type BucketVisibility = "public" | "private";

/** The dialog state restored after the bucket-authorization sign-in. */
export interface PendingBucketAuthorization {
  paperId: string;
  bucketId: string;
  destinationMode: BucketDestination;
  visibility: BucketVisibility;
  selectedIds: string[];
}

const REPO_PART_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const BUCKET_ID_RE = /^[A-Za-z0-9][\w.-]*\/[A-Za-z0-9][\w.-]*$/;
const DIRECT_COPY_BATCH_SIZE = 20;
const BUCKET_AUTHORIZATION_PARAM = "copy_to_bucket";

/** The bucket's Hub page, or null when `bucketId` is not a valid namespace/name. */
export function huggingFaceBucketUrl(bucketId: string): string | null {
  const normalized = bucketId.trim();
  if (!BUCKET_ID_RE.test(normalized)) return null;
  const [namespace, name] = normalized.split("/");
  return `https://huggingface.co/buckets/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}`;
}

const pendingAuthorizationKey = (paperId: string) => `pwc:bucket-copy:${paperId}`;

/** Saves the dialog and returns the URL to come back to once authorized. */
export function stashBucketAuthorization(pending: PendingBucketAuthorization): string {
  const returnUrl = new URL(window.location.href);
  returnUrl.searchParams.set(BUCKET_AUTHORIZATION_PARAM, pending.paperId);
  window.sessionStorage.setItem(pendingAuthorizationKey(pending.paperId), JSON.stringify(pending));
  return returnUrl.toString();
}

/** The dialog saved before signing in, when this page load is the return from it. */
export function loadPendingBucketAuthorization(paperId: string): PendingBucketAuthorization | null {
  if (typeof window === "undefined") return null;
  const url = new URL(window.location.href);
  if (url.searchParams.get(BUCKET_AUTHORIZATION_PARAM) !== paperId) return null;

  try {
    const raw = window.sessionStorage.getItem(pendingAuthorizationKey(paperId));
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

/** Forgets the saved dialog and drops the return marker from the address bar. */
export function clearPendingBucketAuthorization(paperId: string): void {
  window.sessionStorage.removeItem(pendingAuthorizationKey(paperId));
  const url = new URL(window.location.href);
  url.searchParams.delete(BUCKET_AUTHORIZATION_PARAM);
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
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

/** The selected Hub repositories, which the server can copy without the CLI. */
export function directBucketArtifacts(artifacts: BucketArtifact[]): DirectBucketArtifact[] {
  return artifacts.flatMap((artifact) =>
    artifact.kind !== "pdf" && artifact.kind !== "github" && artifact.repoId
      ? [{ kind: artifact.kind, repo_id: artifact.repoId }]
      : [],
  );
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

/**
 * A GitHub repository as copied into the bucket. Unlike `parseGitHubRepoUrl`,
 * this keeps the owner/repo casing (it names the bucket folder) and accepts
 * deep links such as `/tree/main`.
 */
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
