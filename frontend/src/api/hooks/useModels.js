import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "./_utils";
import { getToken } from "../tokenBus";
import { fetchModelCatalog } from "../modelCatalog.js";

export function useModels(params = {}) {
  return useQuery({
    queryKey: ["models", params],
    enabled: !!getToken(),
    queryFn: () => fetchModelCatalog(fetchJson, params),
  });
}

export function useModel(modelId) {
  return useQuery({
    queryKey: ["model", modelId],
    enabled: !!getToken() && !!modelId,
    queryFn: () => fetchJson(`/models/${encodeURIComponent(modelId)}`),
  });
}
