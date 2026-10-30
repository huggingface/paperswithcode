/**
 * React hooks for fetching evaluation data using TanStack Query
 */

import { useQuery } from '@tanstack/react-query';
import { evaluationsApi } from '@/lib/api/evaluations';
import { evaluationQueryKeys } from "@/lib/api/queryKeys";

/**
 * Fetch all evaluations for a specific paper
 */
export function useEvaluationsByPaper(paperId: string | undefined, enabled: boolean = true) {
  return useQuery({
    queryKey: evaluationQueryKeys.byPaper(paperId),
    queryFn: () => {
      if (!paperId) throw new Error('Paper ID is required');
      return evaluationsApi.byPaper(paperId);
    },
    enabled: enabled && !!paperId,
    staleTime: 0,
    refetchOnMount: 'always',
  });
}
