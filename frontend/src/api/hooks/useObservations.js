import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "./_utils";
import { getToken } from "../tokenBus";

export function useObservations(params) {
  return useQuery({
    queryKey: ["observations", params],
    enabled: !!getToken() && !!params?.dataset_revision_id && !!params?.observation_profile_id && !!params?.from && !!params?.to,
    queryFn: async () => {
      const data = await fetchJson("/observations", { ...params, limit: 1000 });
      return data.items || [];
    },
  });
}
