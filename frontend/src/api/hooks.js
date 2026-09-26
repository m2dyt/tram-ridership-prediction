import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./apiFetch";
import { getToken } from "./tokenBus";

// Моковые данные на случай, если бэкенда (эндпоинтов) еще нет
const MOCK_CAPABILITIES = {
  network_revision_id: "mock-network-1",
  dataset_revision_id: "mock-data-1",
  source_mode: "demo",
  capabilities: {
    some_model_name: "Mock Модель v1.0"
  }
};

const MOCK_ROUTES = {
  items: [
    { id: "route-1", number: "17", name: "Останкино - Медведково" },
    { id: "route-2", number: "11", name: "Останкино - 16-я Парковая ул." },
    { id: "route-3", number: "39", name: "м. Университет - Чистые пруды" }
  ]
};

const MOCK_ROUTE_DETAILS = {
  id: "route-1",
  number: "17",
  name: "Останкино - Медведково",
  stops: [
    { id: "s1", name: "Останкино", geometry: { type: "Point", coordinates: [37.6173, 55.823] } },
    { id: "s2", name: "ВДНХ", geometry: { type: "Point", coordinates: [37.640, 55.825] } },
    { id: "s3", name: "Ростокино", geometry: { type: "Point", coordinates: [37.665, 55.845] } },
    { id: "s4", name: "Бабушкинская", geometry: { type: "Point", coordinates: [37.663, 55.869] } },
    { id: "s5", name: "Медведково", geometry: { type: "Point", coordinates: [37.661, 55.887] } },
    { id: "s6", name: "Остановка 6", geometry: { type: "Point", coordinates: [37.651, 55.882] } },
    { id: "s7", name: "Остановка 7", geometry: { type: "Point", coordinates: [37.641, 55.872] } }
  ],
  directions: [
    {
      geometry: {
        type: "LineString",
        coordinates: [
          [37.6173, 55.823],
          [37.640, 55.825],
          [37.665, 55.845],
          [37.663, 55.869],
          [37.661, 55.887]
        ]
      }
    }
  ]
};


export function useCapabilities() {
  return useQuery({
    queryKey: ["capabilities"],
    enabled: !!getToken(),
    queryFn: async () => {
      try {
        const res = await apiFetch("/capabilities");
        return await res.json();
      } catch (err) {
        console.warn("Бэкенд недоступен, используем моковые данные capabilities", err);
        return MOCK_CAPABILITIES;
      }
    }
  });
}

export function useRoutes(networkId, validAt) {
  return useQuery({
    queryKey: ["routes", networkId, validAt],
    enabled: !!getToken() && !!networkId && !!validAt,
    queryFn: async () => {
      try {
        const res = await apiFetch(`/routes?network_revision_id=${networkId}&valid_at=${validAt}`);
        const data = await res.json();
        return data.items || [];
      } catch (err) {
        console.warn("Бэкенд недоступен, используем моковые данные маршрутов", err);
        return MOCK_ROUTES.items;
      }
    }
  });
}

export function useRoute(id, networkId, validAt) {
    return useQuery({
      queryKey: ["route", id, networkId, validAt],
      enabled: !!getToken() && !!id && !!networkId && !!validAt,
      queryFn: async () => {
        try {
          const res = await apiFetch(`/routes/${encodeURIComponent(id)}?network_revision_id=${networkId}&valid_at=${validAt}`);
          return await res.json();
        } catch (err) {
          console.warn(`Бэкенд недоступен, используем моковые данные маршрута ${id}`, err);
          return MOCK_ROUTE_DETAILS; // Для демо возвращаем одни и те же детали
        }
      }
    });
}
