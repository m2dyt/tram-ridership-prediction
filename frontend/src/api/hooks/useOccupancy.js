import { useQuery, useMutation } from "@tanstack/react-query";
import { fetchJson } from "./_utils";
import { apiFetch } from "../apiFetch";
import { getToken } from "../tokenBus";

export function useOccupancyTrips(params = {}) {
  return useQuery({
    queryKey: ["occupancy-trips", params],
    enabled: !!getToken(),
    queryFn: async () => {
      const data = await fetchJson("/occupancy-trips", params);
      return data.items || [];
    },
  });
}

export function useCreateOccupancyTrip() {
  return useMutation({
    mutationFn: async (payload) => {
      const res = await apiFetch("/occupancy-trips", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      return res.json();
    },
  });
}

export function useOccupancyTrip(tripId) {
  return useQuery({
    queryKey: ["occupancy-trip", tripId],
    enabled: !!getToken() && !!tripId,
    queryFn: () => fetchJson(`/occupancy-trips/${encodeURIComponent(tripId)}`),
  });
}

export function useOccupancyEvents(tripId) {
  return useQuery({
    queryKey: ["occupancy-events", tripId],
    enabled: !!getToken() && !!tripId,
    queryFn: () => fetchJson(`/occupancy-trips/${encodeURIComponent(tripId)}/events`),
  });
}

export function useApplyOccupancyEvent(tripId) {
  return useMutation({
    mutationFn: async (payload) => {
      const res = await apiFetch(`/occupancy-trips/${encodeURIComponent(tripId)}/events`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      return res.json();
    },
  });
}

export function useCalculateFleetScenario() {
  return useMutation({
    mutationFn: async (payload) => {
      const res = await apiFetch("/scenarios/fleet", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      return res.json();
    },
  });
}
