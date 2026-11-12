import React, { useEffect, useState } from "react";
import {
  Badge,
  Download,
  Empty,
  ErrorBox,
  Loading,
} from "../components/Common.jsx";
import {
  useForecastRuns,
  useForecastRun,
  useCreateForecastRun,
  useForecastPoints,
  useForecastMap,
  useMe,
} from "../api/hooks";
import Chart from "../components/Chart.jsx";
import Map from "../components/Map.jsx";
import ForecastAggregate from "./ForecastAggregate.jsx";
import { levelName, spatialLabel } from "../domain/aggregate.js";
import {
  explainForecastText,
  forecastCoverageLabel,
  forecastDateRange,
  forecastIssue,
  forecastModelLabel,
} from "../domain/forecast.js";
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

export default function Forecast({ caps, route }) {
  const userQuery = useMe();
  const profiles = caps.forecast_profiles.filter((p) =>
    p.route_ids.includes(route.route.id),
  );
  const [profileId, setProfileId] = useState(profiles[0]?.id || "");
  const profile = profiles.find((p) => p.id === profileId) || profiles[0];
  const [start, setStart] = useState(""),
    [asOf, setAsOf] = useState(""),
    [runId, setRunId] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(null);

  useEffect(() => {
    setStart(localInput(profile?.forecast_start_min));
    setAsOf(localInput(profile?.allowed_as_of_end));
    setRunId("");
  }, [profile?.id]);

  const runsQuery = useForecastRuns(
    profile
      ? {
          dataset_revision_id: caps.dataset_revision_id,
          profile_id: profile.id,
          route_id: route.route.id,
        }
      : {},
  );
  const runs = {
    data: runsQuery.data,
    loading: runsQuery.isLoading,
    error: runsQuery.error,
  };

  const selectedId = runId || runs.data?.[0]?.id;

  const runQuery = useForecastRun(selectedId);
  const run = {
    data: runQuery.data,
    loading: runQuery.isLoading,
    error: runQuery.error,
  };

  const createMutation = useCreateForecastRun();
  const issue = forecastIssue({
    profile,
    role: userQuery.data?.role,
    start,
    asOf,
  });
  async function create(e) {
    e.preventDefault();
    if (issue) return;
    setBusy(true);
    setError(null);
    try {
      const result = await createMutation.mutateAsync({
        dataset_revision_id: caps.dataset_revision_id,
        profile_id: profile.id,
        route_ids: [route.route.id],
        as_of: moscowTime(asOf),
        forecast_start: moscowTime(start),
      });
      setRunId(result.id);
      runsQuery.refetch();
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
            <h2>Прогноз пассажиропотока</h2>
            <p className="forecast-intro">
              Выберите период для маршрута {route.route.number}, затем запустите
              расчёт. После завершения можно изучить график, карту и итоги за
              выбранный промежуток.
            </p>
          </div>
        </div>
        <form className="form-grid" onSubmit={create}>
          <label>
            Период и детализация
            <select
              value={profile.id}
              onChange={(e) => setProfileId(e.target.value)}
            >
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {horizonName(p.horizon)} · {unitName(p.metric)} ·{" "}
                  {{ hour: "по часам", day: "по дням", month: "по месяцам" }[
                    p.resolution
                  ] || p.resolution}
                  {levelName(p.spatial_level)}
                  {p.availability !== "available" ? " · недоступно" : ""}
                </option>
              ))}
            </select>
          </label>
          <label>
            Начало прогноза, Москва
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
            Данные доступны на дату, Москва
            <input
              required
              type="datetime-local"
              value={asOf}
              min={localInput(profile.allowed_as_of_start)}
              max={localInput(profile.allowed_as_of_end)}
              onChange={(e) => setAsOf(e.target.value)}
            />
          </label>
          <button disabled={busy || Boolean(issue)}>
            {busy ? "Создаём…" : "Рассчитать прогноз ↗"}
          </button>
        </form>
        <div className="forecast-hint">
          <p>
            Дата доступных данных ограничивает историю, которую расчёт может
            использовать. Все даты указаны по московскому времени.
          </p>
          <p>
            Начало прогноза:{" "}
            {forecastDateRange(
              profile.forecast_start_min,
              profile.forecast_start_max,
            )}
            . Данные доступны на дату:{" "}
            {forecastDateRange(
              profile.allowed_as_of_start,
              profile.allowed_as_of_end,
            )}
            .
            {profile.start_alignment === "month_start"
              ? " Начало — первое число месяца в 00:00."
              : profile.start_alignment === "local_midnight"
                ? " Начало — в 00:00."
                : ""}
          </p>
          {profile.limitations?.map((limitation, index) => (
            <p key={index}>{explainForecastText(limitation)}</p>
          ))}
        </div>
        {issue && (
          <p className="notice" role="status">
            {explainForecastText(issue)}
          </p>
        )}
        <ErrorBox error={userQuery.error} />
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
              runsQuery.refetch();
              runQuery.refetch();
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
          {run.data.status === "queued"
            ? "Расчёт ожидает обработки."
            : "Расчёт выполняется."}{" "}
          Состояние обновляется автоматически.
        </div>
      )}
      {run.data?.status === "succeeded" ? (
        <Result key={run.data.id} run={run.data} route={route} />
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

function Result({ run, route }) {
  const [index, setIndex] = useState(0),
    [series, setSeries] = useState("");

  const resultQuery = useForecastPoints(run.id, {
    from: run.forecast_start,
    to: run.forecast_end,
    route_id: route.route.id,
  });
  const result = {
    data: resultQuery.data,
    loading: resultQuery.isLoading,
    error: resultQuery.error,
  };

  const keys = [...new Set((result.data || []).map(seriesKey))];
  const selected = series || keys[0];
  const points = (result.data || []).filter((p) => seriesKey(p) === selected);
  const at = points[index]?.interval_start;

  const mapParams =
    at && points[0]?.spatial
      ? {
          ...Object.fromEntries(
            Object.entries(points[0].spatial).filter(
              ([key]) => key !== "level",
            ),
          ),
          interval_start: at,
        }
      : null;

  const mapQuery = useForecastMap(run.id, mapParams || {});

  const mapData = mapQuery.data
    ? {
        type: "FeatureCollection",
        features: (mapQuery.data.features || []).filter(
          (f) => seriesKey(f.properties) === selected,
        ),
      }
    : null;

  const map = {
    data: mapData,
    loading: mapQuery.isLoading,
    error: mapQuery.error,
  };
  const values = points.map((p) => p.value).filter((v) => v != null);
  const max = values.length ? Math.max(...values) : null;
  return (
    <>
      <section className="panel forecast-result-summary">
        <div className="section-heading">
          <div>
            <h2>Результат расчёта</h2>
            <p className="muted">
              Маршрут {route.route.number} · {horizonName(run.profile.horizon)}{" "}
              · {unitName(run.profile.metric)}
            </p>
          </div>
          <Badge>{forecastModelLabel(run.model)}</Badge>
        </div>
        <p>
          Период прогноза: с {date(run.forecast_start)} до{" "}
          {date(run.forecast_end)}, не включая конечный момент. История доступна
          на {date(run.as_of)}.
        </p>
        {run.warnings?.length > 0 && (
          <ul>
            {run.warnings.map((warning, index) => (
              <li key={index}>{explainForecastText(warning)}</li>
            ))}
          </ul>
        )}
      </section>
      <div className="stat-grid">
        <div className="stat">
          <span>Пик выбранного ряда</span>
          <strong>
            {result.loading
              ? "Загрузка…"
              : result.error
                ? "Нет данных"
                : number(max)}
          </strong>
          <small>{unitName(run.profile.metric)} за интервал</small>
        </div>
        <div className="stat">
          <span>Покрытие прогноза</span>
          <strong>
            {forecastCoverageLabel({
              loading: result.loading,
              error: result.error,
              points,
            })}
          </strong>
          <small>интервалов со значением</small>
        </div>
        <div className="stat">
          <span>Метод</span>
          {run.model?.method === "tram_bundle" ? (
            <>
              <strong className="word-stat">
                {run.model.is_baseline
                  ? "Базовая модель по сезонному профилю"
                  : "Обученная модель"}
              </strong>
              <small>
                Версия {run.model.version}{" "}
                {run.model.training_history_end && (
                  <>
                    ·{" "}
                    {run.model.is_baseline
                      ? "исторические данные до"
                      : "данные для обучения до"}{" "}
                    {new Intl.DateTimeFormat("ru-RU", {
                      timeZone: "Europe/Moscow",
                      day: "2-digit",
                      month: "short",
                      year: "numeric",
                    }).format(new Date(run.model.training_history_end))}
                  </>
                )}
              </small>
            </>
          ) : run.model?.method === "seasonal_naive_v1" ? (
            <>
              <strong className="word-stat">Сезонная база</strong>
              <small>Версия {run.model.version} · обучение не требуется</small>
            </>
          ) : (
            <>
              <strong className="word-stat">
                {forecastModelLabel(run.model)}
              </strong>
              <small>Метод указан в параметрах расчёта</small>
            </>
          )}
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
                    <option key={k} value={k}>
                      {spatialLabel(JSON.parse(k), route)}
                    </option>
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
            {points.some((p) => p.prediction_interval) && (
              <p className="muted">
                Полоса на графике: диапазон, в который фактическое значение
                попадало примерно в{" "}
                {Math.round(
                  (points.find((p) => p.prediction_interval)
                    ?.prediction_interval.nominal_coverage || 0) * 100,
                )}{" "}
                % часов на отложенной проверке модели.
              </p>
            )}
            <p className="muted">
              Карта: выбранный маршрут и интервал. График: один пространственный
              ряд. Расчёт {run.id.slice(0, 8)} · данные на {date(run.as_of)}.
            </p>
          </>
        )}
      </section>
      <ForecastAggregate run={run} route={route} />
    </>
  );
}
