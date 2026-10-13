import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getApiErrorMessage } from "@/lib/apiTransport";
import { submissionsApi } from "@/lib/api/submissions";
import { pendingEditSubmission } from "@/lib/pendingEdits";

const ACCEPTED_LOGO_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];
const LOGO_MAX_BYTES = 2 * 1024 * 1024;

type Logo = { file_name: string; mime_type: string; data_url: string };

function readLogo(file: File): Promise<Logo> {
  if (!ACCEPTED_LOGO_TYPES.includes(file.type)) {
    return Promise.reject(new Error("Choose a JPEG, PNG, WebP, or GIF logo."));
  }
  if (file.size > LOGO_MAX_BYTES) {
    return Promise.reject(new Error("Logo must be 2 MB or smaller."));
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () =>
      resolve({ file_name: file.name, mime_type: file.type, data_url: String(reader.result) });
    reader.onerror = () => reject(new Error("Could not read that logo."));
    reader.readAsDataURL(file);
  });
}

interface Props {
  paperId: string;
  initialName: string;
}

/** Queue a missing organization for admin review; approval also tags the paper. */
export function SuggestOrganizationForm({ paperId, initialName }: Props) {
  const [name, setName] = useState(initialName);
  const [hfSlug, setHfSlug] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [logo, setLogo] = useState<Logo | null>(null);
  const [logoError, setLogoError] = useState("");
  const suggest = useMutation({
    mutationFn: () =>
      submissionsApi.submit(
        pendingEditSubmission(Number(paperId), "new_organization", {
          name: name.trim(),
          ...(hfSlug.trim() ? { hf_slug: hfSlug.trim() } : {}),
          ...(websiteUrl.trim() ? { website_url: websiteUrl.trim() } : {}),
          ...(logo ? { image: logo } : {}),
        }),
      ),
  });

  if (suggest.isSuccess) {
    return (
      <p className="rounded border p-3 text-sm">
        Thanks! "{name.trim()}" was submitted for review. Once an admin approves it, the organization
        is created and added to this paper.
      </p>
    );
  }

  return (
    <form
      className="space-y-2 rounded border p-3"
      onSubmit={(event) => {
        event.preventDefault();
        suggest.mutate();
      }}
    >
      <p className="text-sm font-medium">Suggest a new organization</p>
      <Input aria-label="Organization name" placeholder="Name" value={name} maxLength={200} onChange={(event) => setName(event.target.value)} />
      <Input
        aria-label="Hugging Face organization"
        placeholder="Hugging Face organization (e.g. https://huggingface.co/PrimeIntellect)"
        value={hfSlug}
        onChange={(event) => setHfSlug(event.target.value)}
      />
      <Input
        aria-label="Website"
        type="url"
        placeholder="Website (e.g. https://www.primeintellect.ai)"
        value={websiteUrl}
        onChange={(event) => setWebsiteUrl(event.target.value)}
      />
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        Logo (optional)
        <input
          aria-label="Logo"
          type="file"
          accept={ACCEPTED_LOGO_TYPES.join(",")}
          onChange={(event) => {
            const file = event.target.files?.[0];
            setLogo(null);
            setLogoError("");
            if (file) readLogo(file).then(setLogo, (error: Error) => setLogoError(error.message));
          }}
        />
      </label>
      {logo && <img src={logo.data_url} alt="Selected logo" className="h-12 w-12 rounded border object-contain" />}
      {logoError && <p className="text-sm text-destructive">{logoError}</p>}
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">An admin reviews every new organization.</p>
        <Button
          type="submit"
          variant="outline"
          disabled={!name.trim() || (!hfSlug.trim() && !websiteUrl.trim()) || suggest.isPending}
        >
          {suggest.isPending ? "Submitting..." : "Submit for review"}
        </Button>
      </div>
      {suggest.error && <p className="text-sm text-destructive">{getApiErrorMessage(suggest.error, "Could not submit this organization.")}</p>}
    </form>
  );
}
