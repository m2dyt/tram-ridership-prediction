import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import { apiFetch } from "../apiFetch.js";
import { fetchPages } from "../observationPages.js";
import { fetchJson } from "./_utils.js";
import { demandRequestKey, findDemandRun } from "../../domain/mapDemand.js";

const runPath = (id) => `/forecast-runs/${encodeURIComponent(id)}`;
const pending = (run) => ["queued", "running"].includes(run?.status);

export function useDemandNetwork(revision, days) {
  return useQuery({
    queryKey: ["map-demand-network", revision, days],
    enabled: days.length > 0,
    staleTime: Infinity,
    queryFn: async () => {
      const pages = await Promise.all(
        days.map((day) =>
          fetchJson("/network", {
            network_revision_id: revision,
            valid_at: day,
          }),
        ),
      );
      const routes = new Map();
      for (const page of pages) {
        for (const item of page.items) routes.set(item.route.id, item);
      }
      return [...routes.values()];
    },
  });
}

export function useMapDemand(plan, user) {
  const preparation = useQuery({
    queryKey: ["map-demand-runs", plan],
    enabled: Boolean(user && plan.length),
    staleTime: 30000,
    retry: false,
    // Просмотр карты только ищет готовые расчёты и ничего не ставит в очередь.
    // Сервер отбирает расчёты по профилю и дате начала, поэтому список не растёт
    // вместе с базой.
    queryFn: async () =>
      Promise.all(
        plan.map(async (request) => {
          const runs = await fetchPages(fetchJson, "/forecast-runs", {
            dataset_revision_id: request.dataset_revision_id,
            profile_id: request.profile_id,
            forecast_start: request.forecast_start,
          });
          return { request, run: findDemandRun(runs, request) };
        }),
      ),
  });

  // Недостающие расчёты оператор запускает сам кнопкой. Ключ повтора зависит
  // только от запроса, поэтому повторное нажатие не создаёт второе задание.
  const creation = useMutation({
    mutationFn: async (requests) => {
      for (const request of requests) {
        await apiFetch("/forecast-runs", {
          method: "POST",
          body: JSON.stringify(request),
          headers: { "Idempotency-Key": await demandRequestKey(request) },
        });
      }
    },
    onSettled: () => preparation.refetch(),
  });

  const items = preparation.data || [];
  const runIds = [
    ...new Set(items.flatMap(({ run }) => (run ? [run.id] : []))),
  ];
  const statuses = useQueries({
    queries: runIds.map((id) => ({
      queryKey: ["map-demand-status", id],
      queryFn: () => fetchJson(runPath(id)),
      initialData: () => items.find(({ run }) => run?.id === id)?.run,
      staleTime: 5000,
      refetchInterval: (query) => (pending(query.state.data) ? 2000 : false),
    })),
  });
  const results = useQueries({
    queries: runIds.map((id, index) => ({
      queryKey: ["map-demand-points", id],
      enabled: statuses[index].data?.status === "succeeded",
      staleTime: Infinity,
      queryFn: () =>
        fetchPages(fetchJson, `${runPath(id)}/points`, {
          from: statuses[index].data.forecast_start,
          to: statuses[index].data.forecast_end,
        }),
    })),
  });

  const points = results.flatMap((result, index) => {
    const routeIds = new Set(
      items
        .filter(({ run }) => run?.id === runIds[index])
        .flatMap(({ request }) => request.route_ids),
    );
    return (result.data || []).filter((point) =>
      routeIds.has(point.spatial.route_id),
    );
  });

  const ready = results.filter((result) => result.isSuccess).length;
  const errors = [
    preparation.error?.message,
    ...statuses.map(
      (status) => status.error?.message || status.data?.failure?.message,
    ),
    ...results.map((result) => result.error?.message),
  ].filter(Boolean);
  return {
    points,
    ready,
    total: plan.length,
    loading:
      preparation.isLoading ||
      statuses.some((status) => pending(status.data)) ||
      results.some((result) => result.isLoading),
    unavailable: items.filter(({ run }) => !run).length,
    canCreate: user?.role === "operator",
    creating: creation.isPending,
    createMissing: () =>
      creation.mutate(
        items.filter(({ run }) => !run).map(({ request }) => request),
      ),
    errors: [...new Set([...errors, creation.error?.message].filter(Boolean))],
    retry: async () => {
      await Promise.all(
        [...statuses, ...results.filter((result) => result.isError)]
          .filter((query) => query.isError)
          .map((query) => query.refetch()),
      );
      await preparation.refetch();
    },
  };
}
