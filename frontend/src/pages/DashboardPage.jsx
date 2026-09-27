import React, { useMemo } from "react";
import Chart from "../components/Chart";
import { useObservations, useDataStatus, useHealth } from "../api/hooks";

export default function DashboardPage({ caps, route }) {
  // Find a valid observation profile for the current route
  const profile = useMemo(() => {
    return caps?.observation_profiles?.find(p => p.route_ids?.includes(route?.route?.id)) || caps?.observation_profiles?.[0];
  }, [caps, route]);

  // Fetch observations for the last 30 days of available history (or 24h fallback)
  const { fromDate, toDate, periodLabel } = useMemo(() => {
    if (profile?.history_end) {
      const end = new Date(profile.history_end);
      const start = new Date(end);
      start.setDate(start.getDate() - 30);
      return { 
        fromDate: start.toISOString(), 
        toDate: end.toISOString(),
        periodLabel: "за последние 30 дней наблюдений"
      };
    }
    const end = new Date();
    const start = new Date(end);
    start.setDate(start.getDate() - 1);
    return { 
      fromDate: start.toISOString(), 
      toDate: end.toISOString(),
      periodLabel: "за последние 24 часа"
    };
  }, [profile?.history_end]);

  const observationsQuery = useObservations(profile?.id && route?.route?.id ? {
    dataset_revision_id: caps?.dataset_revision_id,
    observation_profile_id: profile?.id,
    route_id: route?.route?.id,
    from: fromDate,
    to: toDate
  } : null);

  const dashboardPoints = useMemo(() => {
    if (!observationsQuery.data) return [];
    return observationsQuery.data.filter(p => p.spatial?.route_id === route?.route?.id);
  }, [observationsQuery.data, route?.route?.id]);

  const dataStatusQuery = useDataStatus();
  const healthQuery = useHealth();
  const validationSource = dataStatusQuery.data?.sources?.find(source => source.source === "validations");

  return (
    <>
      <div className="mgt-page-hero">
        <div className="mgt-page-hero-content">
          <div className="mgt-page-hero-title">Оперативный дашборд сети</div>
          <p className="mgt-page-hero-desc">
            Сводные аналитические показатели ревизии маршрутной сети, профилей наблюдений и расчётного суточного спроса.
          </p>
        </div>
        <div className="mgt-page-hero-badge">Мосгортранс · Аналитика</div>
      </div>

      <div className="panel">
        <div className="stat-grid">
            <div className="stat stat-pattern">
                <span>Используемая модель</span>
                <strong className="word-stat">
                  {healthQuery.data?.model === "ok" && healthQuery.data?.model_version
                    ? `ML · ${healthQuery.data.model_version}`
                    : healthQuery.data?.model === "fallback"
                      ? "Сезонный резерв"
                      : "Нет активной модели"}
                </strong>
            </div>
            <div className="stat stat-pattern">
                <span>Ревизия сети</span>
                <strong className="word-stat">{caps?.network_revision_id || "Нет данных"}</strong>
            </div>
            <div className="stat stat-pattern">
                <span>Режим данных</span>
                <strong className="word-stat">{caps?.source_mode || "Нет данных"}</strong>
            </div>
            <div className="stat stat-pattern">
                <span>Прогнозируемых маршрутов</span>
                <strong className="word-stat">{profile?.route_ids?.length ?? "—"}</strong>
            </div>
        </div>

       {dataStatusQuery.data && (
         <div className="panel" style={{ marginTop: '2rem', backgroundColor: 'var(--bg-panel)', padding: '1.5rem', borderRadius: '12px' }}>
           <h3 style={{ marginTop: 0 }}>Качество и покрытие данных</h3>
           <div className="stat-grid" style={{ marginTop: '1rem' }}>
             <div className="stat">
                 <span>Качество источника</span>
                 <strong className="word-stat">
                   {validationSource?.quality?.status || "Нет данных"}
                 </strong>
             </div>
             <div className="stat">
                 <span>Покрытие</span>
                 <strong>{validationSource?.quality?.coverage_ratio != null
                   ? `${(validationSource.quality.coverage_ratio * 100).toFixed(1)}%`
                   : "Нет данных"}</strong>
             </div>
             <div className="stat">
                 <span>Последняя проверка API</span>
                 <strong className="word-stat">{new Date(dataStatusQuery.data.checked_at).toLocaleString("ru-RU")}</strong>
             </div>
           </div>
           {(dataStatusQuery.data.warnings || []).length > 0 && (
             <ul>{dataStatusQuery.data.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
           )}
         </div>
       )}

       <div className="panel" style={{ marginTop: '2rem', marginBottom: '2rem' }}>
          <h2>Общий пассажиропоток {periodLabel}</h2>
          <p className="muted">Динамика по маршруту <strong>{route?.route?.number}</strong> ({route?.route?.name}).</p>
          <div style={{ marginTop: '20px' }}>
              {observationsQuery.isLoading ? (
                  <div>Загрузка данных...</div>
              ) : observationsQuery.isError ? (
                  <div style={{ color: 'red' }}>Ошибка загрузки: {observationsQuery.error?.message}</div>
              ) : dashboardPoints.length === 0 ? (
                  <div>Нет данных {periodLabel}.</div>
              ) : (
                  <Chart points={dashboardPoints} fields={["value"]} unit={profile?.metric === "passengers" ? "пасс." : ""} />
              )}
          </div>
       </div>
    </div>
    </>
  );
}
