export function setupMockInterceptor() {
  const originalFetch = window.fetch;

  window.fetch = async (...args) => {
    let [resource, config] = args;
    let url = typeof resource === "string" ? resource : resource.url;

    if (url.startsWith("/api/v1")) {
      console.log("[MOCK API] Intercepted:", url);

      // Parse URL
      const { pathname } = new URL(url, window.location.origin);

      const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      await delay(300); // simulate network delay

      // Helpers
      const jsonResponse = (data, status = 200) => {
        return new Response(JSON.stringify(data), {
          status,
          headers: { "Content-Type": "application/json" }
        });
      };

      // /api/v1/capabilities
      if (pathname === "/api/v1/capabilities") {
        return jsonResponse({
          dataset_revision_id: "mock-data-rev-1",
          network_revision_id: "mock-network-rev-1",
          source_mode: "demo",
          forecast_profiles: [
            {
              id: "profile-1",
              horizon: "day",
              metric: "boardings",
              availability: "available",
              forecast_start_min: "2026-09-01T00:00:00Z",
              forecast_start_max: "2026-09-30T00:00:00Z",
              allowed_as_of_start: "2026-08-01T00:00:00Z",
              allowed_as_of_end: "2026-09-01T00:00:00Z",
              route_ids: ["route-1"]
            }
          ],
          observation_profiles: [
            {
              id: "obs-1",
              step: "hour",
              metric: "validations",
              spatial_levels: ["route", "stop"],
              route_ids: ["route-1"]
            }
          ]
        });
      }

      // /api/v1/data-status
      if (pathname === "/api/v1/data-status") {
        return jsonResponse({
          dataset_revision_id: "mock-data-rev-1",
          network_revision_id: "mock-network-rev-1",
          source_mode: "demo",
          checked_at: new Date().toISOString(),
          sources: [
            { source: "МосТранс", event_watermark: new Date().toISOString(), ingested_at: new Date().toISOString(), freshness: "fresh" }
          ]
        });
      }

      // /api/v1/routes
      if (pathname === "/api/v1/routes") {
        return jsonResponse({
          items: [
            { id: "route-1", number: "17", name: "Останкино - Медведково" },
            { id: "route-2", number: "11", name: "Останкино - 16-я Парковая ул." }
          ]
        });
      }

      // /api/v1/routes/{id}
      if (pathname.match(/^\/api\/v1\/routes\/[^/]+$/)) {
        
        let stopsData = [];
        let shapeData = null;
        try {
          // ИНТЕГРАЦИЯ С DATA.MOS.RU (загрузка заранее скачанного дампа)
          // Дамп генерируется скриптом scripts/fetch_mosru_data.js
          const [resStops, resShape] = await Promise.all([
             originalFetch("/mosru_stops.json"),
             originalFetch("/tram17_shape.json")
          ]);
          if (resStops.ok) {
            stopsData = await resStops.json();
          } else {
            console.warn("Дамп mosru_stops.json не найден, используются хардкод моки.");
          }
          if (resShape.ok) {
             shapeData = await resShape.json();
          }
        } catch(e) {
          console.warn("Не удалось загрузить дампы:", e);
        }

        // Если дамп загрузился - отдаём реальные данные
        if (stopsData && stopsData.length > 0) {
          return jsonResponse({
            route: { id: "route-1", number: "17", name: "Останкино - Медведково (Mos.ru Data)" },
            stops: stopsData,
            directions: [
              {
                id: "dir-1",
                name: "В Медведково",
                geometry: {
                  type: "LineString",
                  coordinates: shapeData ? shapeData.coordinates : stopsData.map(s => s.geometry.coordinates)
                },
                stop_sequence: stopsData.map((s, idx) => ({ stop_id: s.id, sequence: idx + 1 })),
                segments: []
              }
            ]
          });
        }

        return jsonResponse({
          route: {
            id: "route-1",
            number: "17",
            name: "Останкино - Медведково",
          },
          stops: [
            { id: "s1", name: "Останкино", geometry: { type: "Point", coordinates: [37.6173, 55.823] } },
            { id: "s2", name: "ВДНХ", geometry: { type: "Point", coordinates: [37.640, 55.825] } },
            { id: "s3", name: "Медведково", geometry: { type: "Point", coordinates: [37.661, 55.887] } }
          ],
          directions: [
            {
              id: "dir-1",
              name: "В Медведково",
              geometry: {
                type: "LineString",
                coordinates: [[37.6173, 55.823], [37.640, 55.825], [37.661, 55.887]]
              },
              stop_sequence: [
                { stop_id: "s1", sequence: 1 },
                { stop_id: "s2", sequence: 2 },
                { stop_id: "s3", sequence: 3 }
              ],
              segments: []
            }
          ]
        });
      }

      // /api/v1/forecast-runs
      if (pathname === "/api/v1/forecast-runs") {
        if (config?.method === "POST") {
          return jsonResponse({
            id: "run-mock-123",
            status: "succeeded",
            created_at: new Date().toISOString(),
            forecast_start: "2026-09-01T00:00:00Z",
            forecast_end: "2026-09-02T00:00:00Z",
            as_of: "2026-08-31T00:00:00Z",
            profile: { id: "profile-1", metric: "boardings", horizon: "day" },
            model: { id: "model-1", version: "v1.0" }
          });
        }
        return jsonResponse({
          items: [
            {
              id: "run-mock-123",
              status: "succeeded",
              created_at: new Date().toISOString(),
              forecast_start: "2026-09-01T00:00:00Z",
              forecast_end: "2026-09-02T00:00:00Z",
              as_of: "2026-08-31T00:00:00Z",
              profile: { id: "profile-1", metric: "boardings", horizon: "day" },
              model: { id: "model-1", version: "v1.0" }
            }
          ]
        });
      }

      // /api/v1/forecast-runs/{id}
      if (pathname.match(/^\/api\/v1\/forecast-runs\/[^/]+$/)) {
        return jsonResponse({
          id: "run-mock-123",
          status: "succeeded",
          created_at: new Date().toISOString(),
          forecast_start: "2026-09-01T00:00:00Z",
          forecast_end: "2026-09-02T00:00:00Z",
          as_of: "2026-08-31T00:00:00Z",
          profile: { id: "profile-1", metric: "boardings", horizon: "day" },
          model: { id: "model-1", version: "v1.0" }
        });
      }

      // /api/v1/forecast-runs/{id}/points
      if (pathname.match(/^\/api\/v1\/forecast-runs\/[^/]+\/points$/)) {
        return jsonResponse({
          items: [
            { interval_start: "2026-09-01T08:00:00Z", route_id: "route-1", value: 120 },
            { interval_start: "2026-09-01T09:00:00Z", route_id: "route-1", value: 450 },
            { interval_start: "2026-09-01T10:00:00Z", route_id: "route-1", value: 310 }
          ]
        });
      }

      // /api/v1/forecast-runs/{id}/map
      if (pathname.match(/^\/api\/v1\/forecast-runs\/[^/]+\/map$/)) {
        return jsonResponse({
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: { type: "Point", coordinates: [37.640, 55.825] },
              properties: { route_id: "route-1", stop_id: "s2", value: 450 }
            }
          ]
        });
      }

      // /api/v1/observations
      if (pathname === "/api/v1/observations") {
        return jsonResponse({
          items: [
            { interval_start: "2026-08-31T08:00:00Z", route_id: "route-1", value: 110 },
            { interval_start: "2026-08-31T09:00:00Z", route_id: "route-1", value: 420 }
          ]
        });
      }

      // /api/v1/evaluations
      if (pathname === "/api/v1/evaluations") {
        return jsonResponse({ items: [] });
      }

      // === NEW MOCKS FOR MISSING PAGES ===

      // /api/v1/scenarios/fleet (Fleet.jsx)
      if (pathname === "/api/v1/scenarios/fleet") {
        return jsonResponse({
          required_vehicles: 12,
          additional_vehicles: 2,
          maximum_headway_minutes: 5,
          feasible_with_reserve: true,
          reserve_shortfall: 0,
          available_vehicles: 14
        });
      }
      
      // /api/v1/occupancy-trips (Occupancy.jsx)
      if (pathname === "/api/v1/occupancy-trips") {
        if (config?.method === "POST") {
           return jsonResponse({ id: "trip-mock-1" });
        }
        return jsonResponse({ items: [] }); // Возвращаем пустой список (trips), чтобы не падал find
      }
      
      if (pathname.match(/^\/api\/v1\/occupancy-trips\/[^/]+\/events$/)) {
        return jsonResponse({ items: [] });
      }

      // /api/v1/context/snapshots (Context.jsx)
      if (pathname === "/api/v1/context/snapshots") {
        return jsonResponse({ items: [] });
      }
      
      if (pathname === "/api/v1/context/refresh") {
        return jsonResponse({ id: "snap-mock-1" });
      }
      
      if (pathname.match(/^\/api\/v1\/context\/snapshots\/[^/]+$/)) {
        return jsonResponse({ 
           id: "snap-mock-1",
           provider: "open-meteo",
           status: "available",
           record_count: 0,
           available_at: new Date().toISOString(),
           source_url: "https://open-meteo.com",
           attribution: "Weather data by Open-Meteo",
           warnings: [],
           kind: "weather",
           records: []
        });
      }

      // Default mock for unhandled routes
      return jsonResponse({ message: "Mock endpoint not implemented in interceptor" }, 404);
    }

    // Call original fetch for non-API routes
    return originalFetch.apply(window, args);
  };
}
