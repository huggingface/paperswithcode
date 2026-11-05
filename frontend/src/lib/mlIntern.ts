import { stripArxivVersion } from "@/lib/utils";

// Matches the prompt behind the "Reproduce this paper" button on Hugging Face paper pages.
export function mlInternReproducePrompt(title: string, arxivId: string | null | undefined): string {
  const reference = arxivId ? ` (arXiv:${stripArxivVersion(arxivId)})` : "";
  return [
    `Reproduce the central claims of the research paper "${title}"${reference}.`,
    "If it is not feasible to fully reproduce the experiments from the paper, then run smaller-scale experiments that can still validate or falsify the claims.",
    "Publish any trained models, processed datasets, and demos as Hub repos, and upload everything else to a Hugging Face Bucket, with the final report as README.md at the bucket's root linking to them.",
  ].join(" ");
}

export function mlInternReproduceUrl(title: string, arxivId: string | null | undefined): string {
  const params = new URLSearchParams({ mode: "ml-intern", prompt: mlInternReproducePrompt(title, arxivId) });
  return `https://huggingface.co/chat/?${params.toString()}`;
}
