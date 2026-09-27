import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "./_utils";
import { getToken } from "../tokenBus";

export function useModels(params = {}) {
  return useQuery({
    queryKey: ["models", params],
    enabled: !!getToken(),
    queryFn: async () => {
      const data = await fetchJson("/models", params);
      return data.items || [];
    },
  });
}

export function useModel(modelId) {
  return useQuery({
    queryKey: ["model", modelId],
    enabled: !!getToken() && !!modelId,
    queryFn: () => fetchJson(`/models/${encodeURIComponent(modelId)}`),
  });
}
