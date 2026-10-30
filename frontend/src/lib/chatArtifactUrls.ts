import { apiUrl } from "@/lib/apiUrl";

const segment = encodeURIComponent;

/** API paths (relative to `/api/v1`) of private chat artifacts. */
export const chatArtifactPath = (artifactId: string) => `/chat/artifacts/${segment(artifactId)}`;
export const chatArtifactVersionPath = (artifactId: string, versionId: string) => (
  `${chatArtifactPath(artifactId)}/versions/${segment(versionId)}`
);
export const chatArtifactFilePath = (path: string) => path.split("/").map(encodeURIComponent).join("/");

/** Browser URLs for private artifact files (previews, downloads, exports). */
export const chatArtifactUrls = {
  preview: (artifactId: string, versionId: string) => apiUrl(`/api/v1${chatArtifactVersionPath(artifactId, versionId)}/preview`),
  file: (artifactId: string, versionId: string, kind: "source" | "download" | "figures", path: string) => (
    apiUrl(`/api/v1${chatArtifactVersionPath(artifactId, versionId)}/${kind}/${chatArtifactFilePath(path)}`)
  ),
  pdfExport: (artifactId: string) => apiUrl(`/api/v1${chatArtifactPath(artifactId)}/export/pdf`),
  sourceZip: (artifactId: string, versionId: string) => apiUrl(`/api/v1${chatArtifactVersionPath(artifactId, versionId)}/export/source.zip`),
  sharedRoot: (shareId: string, capability: string) => (
    apiUrl(`/api/v1/chat/shares/${segment(shareId)}/artifacts/${segment(capability)}`)
  ),
};
