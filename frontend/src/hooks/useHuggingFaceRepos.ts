import { useQuery } from '@tanstack/react-query';
import { TEN_MINUTES } from '@/lib/api/queryKeys';
import { stripArxivVersion } from '@/lib/utils';

export interface HuggingFaceRepoCounts {
  models: number;
  datasets: number;
  spaces: number;
  /** Full model URLs discovered via the Hub arXiv endpoint. */
  modelUrls: string[];
  /** Full dataset URLs discovered via the Hub arXiv endpoint. */
  datasetUrls: string[];
  /** Full Space URLs discovered via the Hub arXiv endpoint. */
  spaceUrls: string[];
  isLimited: boolean; // Indicates if counts might be higher than displayed
  paperExists: boolean; // Whether huggingface.co/papers/<id> exists
}

const HF_URL_PREFIX: Record<'models' | 'datasets' | 'spaces', string> = {
  models: 'https://huggingface.co/',
  datasets: 'https://huggingface.co/datasets/',
  spaces: 'https://huggingface.co/spaces/',
};

const countFromRepos = (
  reposData: Record<string, unknown[]>,
  type: 'models' | 'datasets' | 'spaces',
): { count: number; isLimited: boolean } => {
  const count = (reposData[type] || []).length;
  if (count < 100) return { count, isLimited: false };
  return { count, isLimited: true };
};

const repoUrlsFromRepos = (
  reposData: Record<string, unknown[]>,
  type: 'models' | 'datasets' | 'spaces',
): string[] => {
  const entries = reposData[type];
  if (!Array.isArray(entries)) return [];

  return entries
    .map((entry) => {
      if (typeof entry === 'string') return entry;
      if (entry && typeof entry === 'object') {
        const record = entry as { id?: string; repoId?: string };
        return record.id || record.repoId || null;
      }
      return null;
    })
    .filter((repoId): repoId is string => !!repoId)
    .map((repoId) => `${HF_URL_PREFIX[type]}${repoId}`);
};

const checkPaperExists = async (arxivId: string): Promise<boolean> => {
  try {
    const response = await fetch(`https://huggingface.co/api/papers/${stripArxivVersion(arxivId)}`);
    return response.ok;
  } catch {
    return false;
  }
};

const fetchHuggingFaceRepos = async (arxivId: string): Promise<HuggingFaceRepoCounts> => {
  const id = stripArxivVersion(arxivId);

  const [reposData, paperExists] = await Promise.all([
    fetch(`https://huggingface.co/api/arxiv/${id}/repos`)
      .then(async (response) => {
        if (!response.ok) {
          console.warn(`Failed to fetch repos for arXiv:${id}, status: ${response.status}`);
          return null;
        }
        return response.json() as Promise<Record<string, unknown[]>>;
      })
      .catch((error) => {
        console.warn(`Failed to fetch repos for arXiv:${id}:`, error);
        return null;
      }),
    checkPaperExists(id),
  ]);

  if (!reposData) {
    return {
      models: 0,
      datasets: 0,
      spaces: 0,
      modelUrls: [],
      datasetUrls: [],
      spaceUrls: [],
      isLimited: false,
      paperExists,
    };
  }

  const modelsResult = countFromRepos(reposData, 'models');
  const datasetsResult = countFromRepos(reposData, 'datasets');
  const spacesResult = countFromRepos(reposData, 'spaces');

  return {
    models: modelsResult.count,
    datasets: datasetsResult.count,
    spaces: spacesResult.count,
    modelUrls: repoUrlsFromRepos(reposData, 'models'),
    datasetUrls: repoUrlsFromRepos(reposData, 'datasets'),
    spaceUrls: repoUrlsFromRepos(reposData, 'spaces'),
    isLimited: modelsResult.isLimited || datasetsResult.isLimited || spacesResult.isLimited,
    paperExists,
  };
};

export const useHuggingFaceRepos = (arxivId: string | null | undefined) => {
  return useQuery({
    queryKey: ['huggingface-repos', arxivId],
    queryFn: () => fetchHuggingFaceRepos(arxivId!),
    enabled: !!arxivId,
    staleTime: TEN_MINUTES,
    retry: 1,
  });
};
