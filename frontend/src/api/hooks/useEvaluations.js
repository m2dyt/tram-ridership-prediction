import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "./_utils";
import { getToken } from "../tokenBus";
import { fetchPages } from "../observationPages.js";

export function useEvaluations(params = {}) {
  return useQuery({
    queryKey: ["evaluations", params],
    enabled: !!getToken(),
    queryFn: () => fetchPages(fetchJson, "/evaluations", params),
  });
}

export function useEvaluation(evaluationId) {
  return useQuery({
    queryKey: ["evaluation", evaluationId],
    enabled: !!getToken() && !!evaluationId,
    queryFn: () =>
      fetchJson(`/evaluations/${encodeURIComponent(evaluationId)}`),
  });
}

export function useEvaluationPoints(evaluationId, params = {}) {
  return useQuery({
    queryKey: ["evaluation-points", evaluationId, params],
    enabled: !!getToken() && !!evaluationId,
    queryFn: () =>
      fetchPages(
        fetchJson,
        `/evaluations/${encodeURIComponent(evaluationId)}/points`,
        params,
      ),
  });
}
