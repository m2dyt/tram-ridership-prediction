import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "./_utils";
import { getToken } from "../tokenBus";

export function useNetwork(networkId, validAt) {
  return useQuery({
    queryKey: ["network", networkId, validAt],
    enabled: !!getToken() && !!networkId && !!validAt,
    queryFn: () => fetchJson("/network", { network_revision_id: networkId, valid_at: validAt }),
  });
}

export function useRoutes(networkId, validAt) {
  return useQuery({
    queryKey: ["routes", networkId, validAt],
    enabled: !!getToken() && !!networkId && !!validAt,
    queryFn: async () => {
      const data = await fetchJson("/routes", { network_revision_id: networkId, valid_at: validAt, limit: 1000 });
      return data.items || [];
    },
  });
}

export function useRoute(routeId, networkId, validAt) {
  return useQuery({
    queryKey: ["route", routeId, networkId, validAt],
    enabled: !!getToken() && !!routeId && !!networkId && !!validAt,
    queryFn: () => fetchJson(`/routes/${encodeURIComponent(routeId)}`, { network_revision_id: networkId, valid_at: validAt }),
  });
}

export function useStops(networkId, validAt, routeId = null) {
  return useQuery({
    queryKey: ["stops", networkId, validAt, routeId],
    enabled: !!getToken() && !!networkId && !!validAt,
    queryFn: async () => {
      const data = await fetchJson("/stops", { network_revision_id: networkId, valid_at: validAt, route_id: routeId, limit: 1000 });
      return data.items || [];
    },
  });
}
