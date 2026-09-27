import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "./_utils";
import { getToken } from "../tokenBus";

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => fetchJson("/health"),
  });
}

export function useCapabilities() {
  return useQuery({
    queryKey: ["capabilities"],
    enabled: !!getToken(),
    queryFn: () => fetchJson("/capabilities"),
  });
}

export function useDataStatus() {
  return useQuery({
    queryKey: ["data-status"],
    enabled: !!getToken(),
    queryFn: () => fetchJson("/data-status"),
    refetchInterval: 10000,
  });
}
