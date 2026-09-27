import { useQuery, useMutation } from "@tanstack/react-query";
import { fetchJson } from "./_utils";
import { apiFetch } from "../apiFetch";
import { getToken } from "../tokenBus";

export function useCreateForecastRun() {
  return useMutation({
    mutationFn: async (payload) => {
      const res = await apiFetch("/forecast-runs", {
        method: "POST",
        body: JSON.stringify(payload),
        headers: { "Idempotency-Key": crypto.randomUUID() },
      });
      return res.json();
    },
  });
}

export function useForecastRuns(params = {}) {
  return useQuery({
    queryKey: ["forecast-runs", params],
    enabled: !!getToken(),
    queryFn: async () => {
      const data = await fetchJson("/forecast-runs", params);
      return data.items || [];
    },
  });
}

export function useForecastRun(runId) {
  return useQuery({
    queryKey: ["forecast-run", runId],
    enabled: !!getToken() && !!runId,
    queryFn: () => fetchJson(`/forecast-runs/${encodeURIComponent(runId)}`),
    refetchInterval: (query) => {
      const data = query?.state?.data;
      return data && (data.status === "queued" || data.status === "running")
        ? 2000
        : false;
    },
  });
}

export function useForecastPoints(runId, params = {}) {
  return useQuery({
    queryKey: ["forecast-points", runId, params],
    enabled: !!getToken() && !!runId,
    queryFn: async () => {
      const data = await fetchJson(
        `/forecast-runs/${encodeURIComponent(runId)}/points`,
        { ...params, limit: 1000 },
      );
      return data.items || [];
    },
  });
}

export function useForecastMap(runId, params = {}) {
  return useQuery({
    queryKey: ["forecast-map", runId, params],
    enabled: !!getToken() && !!runId && !!params?.interval_start,
    queryFn: () =>
      fetchJson(`/forecast-runs/${encodeURIComponent(runId)}/map`, params),
  });
}

export function useForecastAggregate(runId, params) {
  return useQuery({
    queryKey: ["forecast-aggregate", runId, params],
    enabled: !!getToken() && !!runId && !!params,
    placeholderData: (previous) => previous,
    queryFn: () =>
      fetchJson(
        `/forecast-runs/${encodeURIComponent(runId)}/aggregate`,
        params,
      ),
  });
}
