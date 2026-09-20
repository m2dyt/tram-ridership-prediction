import React, { useEffect, useState } from "react";
import {
  Badge,
  Download,
  Empty,
  ErrorBox,
  Loading,
  useResource,
} from "../components/Common.jsx";
import Chart from "../components/Chart.jsx";
import Map from "../components/Map.jsx";
import {
  date,
  horizonName,
  localInput,
  moscowTime,
  number,
  seriesKey,
  statusName,
  unitName,
} from "../domain/format.js";

export default function Forecast({ api, caps, route }) {
  const profiles = caps.forecast_profiles.filter((p) =>
    p.route_ids.includes(route.route.id),
  );
  const [profileId, setProfileId] = useState(profiles[0]?.id || "");
  const profile = profiles.find((p) => p.id === profileId) || profiles[0];
  const [start, setStart] = useState(""),
    [asOf, setAsOf] = useState(""),
    [runId, setRunId] = useState(""),
    [revision, setRevision] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(null);
  useEffect(() => {
    setStart(localInput(profile?.forecast_start_min));
    setAsOf(localInput(profile?.allowed_as_of_end));
    setRunId("");
  }, [profile?.id]);
  const runs = useResource(
    (signal) =>
      profile
        ? api.all(
            "/forecast-runs",
            {
              dataset_revision_id: caps.dataset_revision_id,
              profile_id: profile.id,
              route_id: route.route.id,
            },
            signal,
          )
        : [],
    [api, profile?.id, revision, route.route.id],
  );
  const selectedId = runId || runs.data?.[0]?.id;
  const [poll, setPoll] = useState(0);
  const run = useResource(
    (signal) =>
      selectedId
        ? api.request("/forecast-runs/" + selectedId, { signal })
        : null,
    [api, selectedId, poll],
  );
  useEffect(() => {
    if (!["queued", "running"].includes(run.data?.status)) return;
    const timer = setTimeout(() => setPoll((v) => v + 1), 2000);
    return () => clearTimeout(timer);
  }, [run.data]);
  async function create(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.request("/forecast-runs", {
        body: {
          dataset_revision_id: caps.dataset_revision_id,
          profile_id: profile.id,
          route_ids: [route.route.id],
          as_of: moscowTime(asOf),
          forecast_start: moscowTime(start),
        },
        idempotencyKey: crypto.randomUUID(),
      });
      setRunId(result.id);
      setRevision((v) => v + 1);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (!profile) return <Empty>Для этого маршрута нет профилей прогноза.</Empty>;
  return (
    <>
      <section className="panel controls">
        <div className="section-heading">
          <div>
            <p className="eyebrow">РАСЧЁТ БЕЗ ОБУЧЕНИЯ</p>
            <h2>Прогноз пассажиропотока</h2>
          </div>
          <Badge>Сезонная база</Badge>
        </div>
        <form className="form-grid" onSubmit={create}>
          <label>
            Горизонт
            <select
              value={profile.id}
              onChange={(e) => setProfileId(e.target.value)}
            >
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {horizonName(p.horizon)} · {unitName(p.metric)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Начало, Москва
            <input
              required
              type="datetime-local"
              value={start}
              min={localInput(profile.forecast_start_min)}
              max={localInput(profile.forecast_start_max)}
              onChange={(e) => setStart(e.target.value)}
            />
          </label>
          <label>
            Сведения на момент
            <input
              required
              type="datetime-local"
              value={asOf}
              min={localInput(profile.allowed_as_of_start)}
              max={localInput(profile.allowed_as_of_end)}
              onChange={(e) => setAsOf(e.target.value)}
            />
          </label>
          <button disabled={busy || profile.availability !== "available"}>
            {busy ? "Создаём…" : "Рассчитать прогноз ↗"}
          </button>
        </form>
        <ErrorBox error={error} />
        <div className="run-selector">
          <label>
            Сохранённый расчёт
            <select
              value={selectedId || ""}
              onChange={(e) => setRunId(e.target.value)}
            >
              <option value="">
                {runs.data?.length ? "Последний расчёт" : "Расчётов пока нет"}
              </option>
              {runs.data?.map((r) => (
                <option key={r.id} value={r.id}>
                  {date(r.created_at)} ·{" "}
                  {statusName(
                    r.id === run.data?.id ? run.data.status : r.status,
                  )}{" "}
                  · {r.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          <button
            className="secondary"
            onClick={() => {
              setRevision((v) => v + 1);
              setPoll((v) => v + 1);
            }}
          >
            Обновить
          </button>
        </div>
      </section>
      <ErrorBox error={runs.error || run.error} />
      {run.data?.status === "failed" && (
        <div className="notice error">
          Расчёт завершился ошибкой:{" "}
          {run.data.failure?.message || "Смотрите журнал worker"}
        </div>
      )}
      {["queued", "running"].includes(run.data?.status) && (
        <div className="notice">
          {statusName(run.data.status)}. Worker обрабатывает задание; состояние
          обновляется автоматически.
        </div>
      )}
      {run.data?.status === "succeeded" ? (
        <Result key={run.data.id} api={api} run={run.data} route={route} />
      ) : (
        <section className="panel">
          <Map route={route} />
          <p className="muted">
            Карта маршрутной сети. После расчёта здесь появятся значения
            выбранного интервала.
          </p>
        </section>
      )}
    </>
  );
}

function Result({ api, run, route }) {
  const [index, setIndex] = useState(0),
    [series, setSeries] = useState("");
  const result = useResource(
    (signal) =>
      api.all(
        `/forecast-runs/${run.id}/points`,
        {
          from: run.forecast_start,
          to: run.forecast_end,
          route_id: route.route.id,
        },
        signal,
      ),
    [api, run.id, route.route.id],
  );
  const keys = [...new Set((result.data || []).map(seriesKey))];
  const selected = series || keys[0];
  const points = (result.data || []).filter((p) => seriesKey(p) === selected);
  const at = points[index]?.interval_start;
  const map = useResource(
    (signal) =>
      at
        ? api
            .all(
              `/forecast-runs/${run.id}/map`,
              {
                ...Object.fromEntries(
                  Object.entries(points[0].spatial).filter(
                    ([key]) => key !== "level",
                  ),
                ),
                interval_start: at,
              },
              signal,
              "features",
            )
            .then((features) => ({
              type: "FeatureCollection",
              features: features.filter(
                (f) => seriesKey(f.properties) === selected,
              ),
            }))
        : null,
    [api, run.id, at, route.route.id, selected],
  );
  const values = points.map((p) => p.value).filter((v) => v != null);
  const max = values.length ? Math.max(...values) : null;
  return (
    <>
      <div className="stat-grid">
        <div className="stat">
          <span>Пик выбранного ряда</span>
          <strong>{number(max)}</strong>
          <small>{unitName(run.profile.metric)} за интервал</small>
        </div>
        <div className="stat">
          <span>Покрытие прогноза</span>
          <strong>
            {values.length}
            <em> / {points.length}</em>
          </strong>
          <small>интервалов со значением</small>
        </div>
        <div className="stat">
          <span>Метод</span>
          <strong className="word-stat">Сезонная база</strong>
          <small>Версия {run.model.version} · обучение не требуется</small>
        </div>
      </div>
      <section className="panel">
        <div className="section-heading">
          <h2>Маршрут и динамика</h2>
          <Download points={points} />
        </div>
        <ErrorBox error={result.error || map.error} />
        {result.loading ? (
          <Loading />
        ) : (
          <>
            {keys.length > 1 && (
              <label>
                Ряд (остановка / участок)
                <select
                  value={selected}
                  onChange={(e) => {
                    setSeries(e.target.value);
                    setIndex(0);
                  }}
                >
                  {keys.map((k) => (
                    <option key={k}>{k}</option>
                  ))}
                </select>
              </label>
            )}
            <Map route={route} forecast={map.data} />
            <Chart
              points={points}
              selected={index}
              onSelect={setIndex}
              unit={unitName(run.profile.metric)}
            />
            <p className="muted">
              Карта: выбранный маршрут и интервал. График: один пространственный
              ряд. Расчёт {run.id.slice(0, 8)} · данные на {date(run.as_of)}.
            </p>
          </>
        )}
      </section>
    </>
  );
}
