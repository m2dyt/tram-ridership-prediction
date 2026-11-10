import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "./_utils";
import { getToken } from "../tokenBus";
import { fetchObservationPages } from "../observationPages.js";

export function useObservations(params) {
  return useQuery({
    queryKey: ["observations", params],
    enabled:
      !!getToken() &&
      !!params?.dataset_revision_id &&
      !!params?.observation_profile_id &&
      !!params?.from &&
      !!params?.to,
    queryFn: () => fetchObservationPages(fetchJson, params),
  });
}
