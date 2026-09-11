export type FrameworkPlatform = "gpu" | "cpu" | "apple";

export interface Framework {
  id: string;
  slug: string;
  name: string;
  organization_name?: string | null;
  description: string;
  when_to_use?: string | null;
  platforms: FrameworkPlatform[];
  github_url?: string | null;
  repository?: string | null;
  paper_count: number;
  docs_url?: string | null;
  introducing_paper_arxiv_id?: string | null;
}

interface FrameworkCategory {
  slug: string;
  name: string;
  description?: string | null;
  guide_url?: string | null;
  guide_label?: string | null;
  frameworks: Framework[];
}

interface FrameworkDomain {
  slug: string;
  name: string;
  description: string;
  categories: FrameworkCategory[];
}

export interface FrameworkCatalog {
  domains: FrameworkDomain[];
}

export const PLATFORM_LABELS: Record<FrameworkPlatform, string> = {
  gpu: "GPU",
  cpu: "CPU",
  apple: "Apple silicon",
};
