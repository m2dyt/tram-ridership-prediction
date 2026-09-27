import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "./_utils";
import { getToken } from "../tokenBus";

export function useEvaluations(params = {}) {
  return useQuery({
    queryKey: ["evaluations", params],
    enabled: !!getToken(),
    queryFn: async () => {
      const data = await fetchJson("/evaluations", params);
      return data.items || [];
    },
  });
}

export function useEvaluation(evaluationId) {
  return useQuery({
    queryKey: ["evaluation", evaluationId],
    enabled: !!getToken() && !!evaluationId,
    queryFn: () => fetchJson(`/evaluations/${encodeURIComponent(evaluationId)}`),
  });
}

export function useEvaluationPoints(evaluationId, params = {}) {
  return useQuery({
    queryKey: ["evaluation-points", evaluationId, params],
    enabled: !!getToken() && !!evaluationId,
    queryFn: async () => {
      const data = await fetchJson(`/evaluations/${encodeURIComponent(evaluationId)}/points`, { ...params, limit: 1000 });
      return data.items || [];
    },
  });
}
