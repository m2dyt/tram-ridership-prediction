import React, { useMemo } from "react";
import Chart from "../components/Chart";
import { useObservations, useDataStatus, useHealth } from "../api/hooks";
import { date, unitName } from "../domain/format.js";
import {
  dashboardObservationProfile,
  forecastRouteCount,
  observationWindow,
} from "../domain/dashboardData.js";

const modelLabel = (health) => {
  if (health?.model === "ok")
    return health.model_version
      ? `Подключена · ${health.model_version}`
      : "Подключена";
  if (health?.model === "fallback") return "Ошибка, разрешён резерв";
  if (health?.model === "not_configured") return "Не подключена";
  return "Состояние неизвестно";
};

export default function DashboardPage({ caps, route }) {
  const profile = dashboardObservationProfile(
    caps?.observation_profiles,
    route?.route?.id,
  );
  const window = useMemo(() => observationWindow(profile, 30), [profile]);
  const observationsQuery = useObservations(
    profile?.id && route?.route?.id && window
      ? {
          dataset_revision_id: caps?.dataset_revision_id,
          observation_profile_id: profile.id,
          route_id: route.route.id,
          ...window,
        }
      : null,
  );
  const dashboardPoints = useMemo(
    () =>
      (observationsQuery.data || []).filter(
        (point) => point.spatial?.route_id === route?.route?.id,
      ),
    [observationsQuery.data, route?.route?.id],
  );
  const dataStatusQuery = useDataStatus();
  const healthQuery = useHealth();
  const validationSource = dataStatusQuery.data?.sources?.find(
    (source) => source.source === "validations",
  );
  const quality = {
    verified: "Проверено",
    unverified: "Не проверено",
    degraded: "Есть ограничения",
  };
  const resolution = { hour: "по часам", day: "по дням", month: "по месяцам" };

  return (
    <>
      <div className="mgt-page-hero">
        <div className="mgt-page-hero-content">
          <div className="mgt-page-hero-title">Дашборд маршрутной сети</div>
          <p className="mgt-page-hero-desc">
            Состояние модели и источников, доступность прогнозов и история
            выбранного маршрута.
          </p>
        </div>
        <div className="mgt-page-hero-badge">Мосгортранс · Аналитика</div>
      </div>

      <div className="panel">
        <div className="stat-grid">
          <div className="stat stat-pattern">
            <span>Файл модели</span>
            <strong className="word-stat">
              {healthQuery.isLoading
                ? "Загрузка…"
                : healthQuery.isError
                  ? "Не удалось проверить"
                  : modelLabel(healthQuery.data)}
            </strong>
            <small>Метод конкретного расчёта указан в разделе прогноза.</small>
          </div>
          <div className="stat stat-pattern">
            <span>Версия сети</span>
            <strong className="word-stat">
              {caps?.network_revision_id || "Нет данных"}
            </strong>
          </div>
          <div className="stat stat-pattern">
            <span>Источник данных</span>
            <strong className="word-stat">
              {caps?.source_mode === "demo"
                ? "Демонстрационные"
                : caps?.source_mode === "batch"
                  ? "Пакетная загрузка"
                  : caps?.source_mode || "Нет данных"}
            </strong>
          </div>
          <div className="stat stat-pattern">
            <span>Маршрутов с доступным прогнозом</span>
            <strong className="word-stat">
              {caps ? forecastRouteCount(caps.forecast_profiles) : "—"}
            </strong>
          </div>
        </div>
        {caps?.source_mode === "demo" && (
          <p className="notice">
            На экране синтетические данные. Они не отражают реальный
            пассажиропоток.
          </p>
        )}

        <div
          className="panel"
          style={{
            marginTop: "2rem",
            backgroundColor: "var(--bg-panel)",
            padding: "1.5rem",
            borderRadius: "12px",
          }}
        >
          <h3 style={{ marginTop: 0 }}>Качество и покрытие данных</h3>
          {dataStatusQuery.isLoading ? (
            <p role="status">Загружаем сведения об источниках…</p>
          ) : dataStatusQuery.isError ? (
            <p role="alert">
              Не удалось получить сведения об источниках. Обновите страницу.
            </p>
          ) : (
            <>
              <div className="stat-grid" style={{ marginTop: "1rem" }}>
                <div className="stat">
                  <span>Качество источника валидаций</span>
                  <strong className="word-stat">
                    {quality[validationSource?.quality?.status] ||
                      validationSource?.quality?.status ||
                      "Нет данных"}
                  </strong>
                </div>
                <div className="stat">
                  <span>Покрытие источника</span>
                  <strong>
                    {validationSource?.quality?.coverage_ratio != null
                      ? `${(validationSource.quality.coverage_ratio * 100).toFixed(1)}%`
                      : "Нет данных"}
                  </strong>
                </div>
                <div className="stat">
                  <span>Проверено API</span>
                  <strong className="word-stat">
                    {date(dataStatusQuery.data?.checked_at)}
                  </strong>
                  <small>Время Москвы</small>
                </div>
              </div>
              {(dataStatusQuery.data?.warnings || []).length > 0 && (
                <ul>
                  {dataStatusQuery.data.warnings.map((warning, index) => (
                    <li key={index}>{warning}</li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>

        <div
          className="panel"
          style={{ marginTop: "2rem", marginBottom: "2rem" }}
        >
          <h2>История наблюдений по маршруту {route?.route?.number || "—"}</h2>
          {profile && window ? (
            <p className="muted">
              {unitName(profile.metric)} ·{" "}
              {resolution[profile.resolution] || profile.resolution} ·{" "}
              {date(window.from)} — {date(window.to)} по Москве. Конец периода
              не включён.
            </p>
          ) : (
            <p className="muted">
              Для выбранного маршрута нет подходящего профиля наблюдений.
            </p>
          )}
          <div style={{ marginTop: "20px" }}>
            {observationsQuery.isLoading ? (
              <div role="status">Загрузка данных…</div>
            ) : observationsQuery.isError ? (
              <div role="alert">
                Не удалось загрузить наблюдения. Обновите страницу.
              </div>
            ) : dashboardPoints.length === 0 ? (
              <div>Нет наблюдений за доступный период.</div>
            ) : (
              <Chart
                points={dashboardPoints}
                fields={["value"]}
                unit={unitName(profile?.metric)}
              />
            )}
          </div>
        </div>
      </div>
    </>
  );
}
