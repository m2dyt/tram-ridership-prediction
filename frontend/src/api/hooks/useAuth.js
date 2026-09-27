import { useQuery, useMutation } from "@tanstack/react-query";
import { fetchJson } from "./_utils";
import { apiFetch } from "../apiFetch";
import { getToken, updateToken } from "../tokenBus";

export function useLogin() {
  return useMutation({
    mutationFn: async ({ username, password }) => {
      const res = await apiFetch("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
        credentials: "include"
      });
      return res.json();
    },
    onSuccess: (data) => {
      updateToken(data.access_token);
    }
  });
}

export function useRegister() {
  return useMutation({
    mutationFn: async ({ username, password }) => {
      const res = await apiFetch("/auth/register", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      return res.json();
    }
  });
}

export function useLogout() {
  return useMutation({
    mutationFn: async () => {
      await apiFetch("/auth/logout", { method: "POST", credentials: "include" });
    },
    onSettled: () => {
      updateToken(null);
    }
  });
}

export function useCreateOperator() {
  return useMutation({
    mutationFn: async ({ username, password }) => {
      const res = await apiFetch("/auth/operators", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      return res.json();
    }
  });
}

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    enabled: !!getToken(),
    queryFn: () => fetchJson("/auth/me"),
  });
}
