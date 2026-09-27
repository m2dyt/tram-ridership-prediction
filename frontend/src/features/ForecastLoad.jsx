import React, { useEffect, useMemo, useState } from "react";
import { Badge, ErrorBox, Loading } from "../components/Common.jsx";
import {
  useCreateForecastRun,
  useForecastAggregate,
  useForecastRuns,
  useForecastTripLoad,
} from "../api/hooks";
import { date, number } from "../domain/format.js";
import { forecastHours, strategyName } from "../domain/aggregate.js";

// Expected load of one tram per stop, from the hourly stop-level forecast.
export default function ForecastLoad({ caps, route }) {
  const profile = caps.forecast_profiles.find(
    (p) =>
      p.spatial_level === "stop" &&
      p.resolution === "hour" &&
      p.availability === "available" &&
      p.route_ids.includes(route.route.id),
  );
  const runsQuery = useForecastRuns(
    profile
      ? {
          dataset_revision_id: caps.dataset_revision_id,
          profile_id: profile.id,
          route_id: route.route.id,
          status: "succeeded",
        }
      : {},
  );
  const run = profile ? runsQuery.data?.[0] : null;
  const create = useCreateForecastRun();

  if (!profile)
    return (
      <section className="panel">
        <h2>Наполненность по прогнозу</h2>
        <p className="muted">
          Для этого маршрута нет прогноза посадок по остановкам, поэтому
          наполненность по прогнозу не рассчитывается.
        </p>
      </section>
    );

  async function calculate() {
    await create.mutateAsync({
      dataset_revision_id: caps.dataset_revision_id,
      profile_id: profile.id,
      route_ids: [route.route.id],
      as_of: profile.allowed_as_of_end,
      forecast_start: profile.forecast_start_min,
    });
    // The worker needs a moment; poll until the run is listed as succeeded.
    for (let i = 0; i < 30; i += 1) {
      const { data } = await runsQuery.refetch();
      if (data?.length) return;
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  }

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">ПРОГНОЗ ПОСАДОК → ЗАГРУЗКА ВАГОНА</p>
          <h2>Наполненность по прогнозу</h2>
        </div>
        <Badge tone="amber">Расчётная оценка</Badge>
      </div>
      <ErrorBox error={runsQuery.error || create.error} />
      {runsQuery.isLoading ? (
        <Loading />
      ) : run ? (
        <TripLoad key={run.id} run={run} route={route} />
      ) : (
        <div className="notice">
          Прогноз посадок по остановкам для маршрута ещё не рассчитан.{" "}
          <button type="button" onClick={calculate} disabled={create.isPending}>
            {create.isPending ? "Рассчитываем…" : "Рассчитать прогноз ↗"}
          </button>
        </div>
      )}
    </section>
  );
}

function TripLoad({ run, route }) {
  const hours = forecastHours(run.forecast_start, run.forecast_end);
  const directions = (route.directions || []).filter((d) => d.id);
  const peak = useForecastAggregate(run.id, {
    route_id: route.route.id,
    group_by: "hour",
  });
  const [form, setForm] = useState({
    hour: "",
    direction: directions[0]?.id || "",
    trips: "8",
    capacity: "250",
    strategy: "uniform",
  });
  const set = (patch) => setForm((current) => ({ ...current, ...patch }));
  // Python and JS spell UTC differently ("+00:00" vs "Z"): compare instants.
  const busiest = hours.find(
    (h) =>
      Date.parse(h) === Date.parse(peak.data?.summary?.peak_interval_start),
  );
  useEffect(() => {
    if (busiest && !form.hour) set({ hour: busiest });
  }, [busiest]);

  const hour = form.hour || hours[0];
  const params = useMemo(
    () =>
      Number(form.trips) > 0
        ? {
            route_id: route.route.id,
            direction_id: form.direction || undefined,
            interval_start: hour,
            trips_per_hour: form.trips,
            capacity: Number(form.capacity) > 0 ? form.capacity : undefined,
            strategy: form.strategy,
          }
        : null,
    [form, hour, route.route.id],
  );
  const load = useForecastTripLoad(run.id, params);
  const data = load.data;
  const names = Object.fromEntries(
    (route.stops || []).map((s) => [s.id, s.name]),
  );
  const stopName = (row) =>
    `${row.sequence}. ${names[row.stop_id] || row.stop_id}`;

  return (
    <>
      <form className="form-grid" onSubmit={(e) => e.preventDefault()}>
        <label>
          Час прогноза
          <select value={hour} onChange={(e) => set({ hour: e.target.value })}>
            {hours.map((h) => (
              <option key={h} value={h}>
                {date(h)}
                {h === busiest ? " · пик" : ""}
              </option>
            ))}
          </select>
        </label>
        {directions.length > 1 && (
          <label>
            Направление
            <select
              value={form.direction}
              onChange={(e) => set({ direction: e.target.value })}
            >
              {directions.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Рейсов в час
          <input
            type="number"
            min="1"
            max="60"
            step="1"
            value={form.trips}
            onChange={(e) => set({ trips: e.target.value })}
          />
        </label>
        <label>
          Вместимость вагона (допущение)
          <input
            type="number"
            min="1"
            step="1"
            value={form.capacity}
            onChange={(e) => set({ capacity: e.target.value })}
          />
        </label>
        <label>
          Длительность поездки
          <select
            value={form.strategy}
            onChange={(e) => set({ strategy: e.target.value })}
          >
            {["uniform", "short", "long"].map((s) => (
              <option key={s} value={s}>
                {strategyName(s)}
              </option>
            ))}
          </select>
        </label>
      </form>
      <ErrorBox error={load.error} />
      {load.isLoading && !data ? (
        <Loading />
      ) : data ? (
        <>
          <div className="stat-grid">
            <div className="stat">
              <span>Пик в вагоне</span>
              <strong>{number(data.summary.peak_onboard, 0)}</strong>
              <small>
                после остановки{" "}
                {stopName(
                  data.stops.find(
                    (s) => s.sequence === data.summary.peak_sequence,
                  ),
                )}
              </small>
            </div>
            <div className="stat">
              <span>Заполнение в пике</span>
              <strong>
                {data.summary.peak_occupancy_ratio == null
                  ? "—"
                  : number(data.summary.peak_occupancy_ratio * 100, 0) + "%"}
              </strong>
              <small>
                {data.summary.over_capacity_stops
                  ? `переполнение на ${data.summary.over_capacity_stops} участках`
                  : "без переполнения"}
              </small>
            </div>
            <div className="stat">
              <span>Посадок за рейс</span>
              <strong>{number(data.summary.boardings_per_trip, 0)}</strong>
              <small>
                {data.trips_per_hour} рейсов · {date(data.interval_start)}
              </small>
            </div>
          </div>
          <LoadChart rows={data.stops} capacity={data.capacity} />
          <details>
            <summary>Таблица по остановкам · {data.stops.length}</summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Остановка</th>
                    <th>Вошли</th>
                    <th>Вышли</th>
                    <th>В вагоне дальше</th>
                    <th>Заполнение</th>
                  </tr>
                </thead>
                <tbody>
                  {data.stops.map((row) => (
                    <tr key={row.sequence}>
                      <td>{stopName(row)}</td>
                      <td>{number(row.boardings)}</td>
                      <td>{number(row.alightings)}</td>
                      <td>{number(row.onboard)}</td>
                      <td>
                        {row.occupancy_ratio == null
                          ? "—"
                          : number(row.occupancy_ratio * 100, 0) + "%"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          <p className="muted">
            Посадки часа из прогноза по остановкам делятся поровну между
            рейсами; высадки распределены по допущению о длительности поездки.
            Прогноз по остановкам — оценочное распределение посадок маршрута.
            Расчёт {run.id.slice(0, 8)}; в журнал фактических рейсов не
            записывается.
          </p>
        </>
      ) : null}
    </>
  );
}

function LoadChart({ rows, capacity }) {
  if (!rows.length) return null;
  const width = 950,
    height = 220,
    left = 48,
    bottom = 190;
  const top = Math.max(1, capacity || 0, ...rows.map((r) => r.onboard)) * 1.15;
  const bar = (width - left - 10) / rows.length;
  const y = (v) => bottom - (v / top) * 165;
  return (
    <div className="chart-wrap">
      <svg
        role="img"
        aria-label="Пассажиров в вагоне после каждой остановки"
        viewBox={`0 0 ${width} ${height}`}
        className="chart"
      >
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line
              x1={left}
              x2={width - 10}
              y1={y(top * f)}
              y2={y(top * f)}
              stroke="#e3e9e8"
            />
            <text x={left - 8} y={y(top * f) + 4} textAnchor="end">
              {number(top * f, 0)}
            </text>
          </g>
        ))}
        {rows.map((row, i) => (
          <rect
            key={row.sequence}
            x={left + i * bar + bar * 0.1}
            y={y(row.onboard)}
            width={bar * 0.8}
            height={bottom - y(row.onboard)}
            fill={row.over_capacity ? "#cc3b3b" : "#128a85"}
          >
            <title>
              {row.sequence}: {number(row.onboard)} пасс.
            </title>
          </rect>
        ))}
        {capacity ? (
          <g>
            <line
              x1={left}
              x2={width - 10}
              y1={y(capacity)}
              y2={y(capacity)}
              stroke="#cc7a32"
              strokeDasharray="6 4"
            />
            <text x={width - 12} y={y(capacity) - 6} textAnchor="end">
              вместимость {number(capacity, 0)}
            </text>
          </g>
        ) : null}
        <text x={left} y={height - 8}>
          остановка {rows[0].sequence}
        </text>
        <text x={width - 10} y={height - 8} textAnchor="end">
          остановка {rows.at(-1).sequence}
        </text>
      </svg>
    </div>
  );
}
