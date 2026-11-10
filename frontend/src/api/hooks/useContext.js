import { useQuery, useMutation } from "@tanstack/react-query";
import { fetchJson } from "./_utils";
import { apiFetch } from "../apiFetch";
import { getToken } from "../tokenBus";
import { fetchPages } from "../observationPages.js";

export function useContextSnapshots(params = {}) {
  return useQuery({
    queryKey: ["context-snapshots", params],
    enabled: !!getToken(),
    queryFn: () => fetchPages(fetchJson, "/context/snapshots", params),
  });
}

export function useContextSnapshot(snapshotId) {
  return useQuery({
    queryKey: ["context-snapshot", snapshotId],
    enabled: !!getToken() && !!snapshotId,
    queryFn: () =>
      fetchJson(`/context/snapshots/${encodeURIComponent(snapshotId)}`),
  });
}

export function useContextSnapshotGeojson(snapshotId) {
  return useQuery({
    queryKey: ["context-snapshot-geojson", snapshotId],
    enabled: !!getToken() && !!snapshotId,
    queryFn: () =>
      fetchJson(`/context/snapshots/${encodeURIComponent(snapshotId)}/geojson`),
  });
}

export function useRefreshContext() {
  return useMutation({
    mutationFn: async (payload) => {
      const res = await apiFetch("/context/refresh", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      return res.json();
    },
  });
}
