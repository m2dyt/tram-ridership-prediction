import React, { useMemo } from "react";
import Chart from "../components/Chart";
import { useObservations, useDataStatus } from "../api/hooks";

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
    // The API might return different levels (stop, segment, route). We can just take the first series or aggregate.
    return observationsQuery.data.filter(p => p.value != null);
  }, [observationsQuery.data]);

  const dataStatusQuery = useDataStatus();

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
                <strong className="word-stat">{caps?.capabilities?.some_model_name || "Трамвай ПРОГНОЗ v1"}</strong>
            </div>
            <div className="stat stat-pattern">
                <span>Ревизия сети</span>
                <strong className="word-stat">{caps?.network_revision_id || "Нет данных"}</strong>
            </div>
            <div className="stat stat-pattern">
                <span>Режим данных</span>
                <strong className="word-stat">{caps?.source_mode || "Реальный"}</strong>
            </div>
            <div className="stat stat-pattern">
                <span>Прогнозируемых маршрутов</span>
                <strong className="word-stat">{profile?.route_ids?.length || 10}</strong>
            </div>
        </div>

       {dataStatusQuery.data && (
         <div className="panel" style={{ marginTop: '2rem', backgroundColor: 'var(--bg-panel)', padding: '1.5rem', borderRadius: '12px' }}>
           <h3 style={{ marginTop: 0 }}>Качество и покрытие данных</h3>
           <div className="stat-grid" style={{ marginTop: '1rem' }}>
             <div className="stat">
                 <span>Статус пайплайна</span>
                 <strong className="word-stat" style={{ color: dataStatusQuery.data.status === 'ok' ? 'var(--success)' : 'var(--error)' }}>
                   {dataStatusQuery.data.status === 'ok' ? 'В норме' : 'Ошибка'}
                 </strong>
             </div>
             <div className="stat">
                 <span>Пропуски данных (Gaps)</span>
                 <strong>{dataStatusQuery.data.gaps_count || 0}</strong>
             </div>
             <div className="stat">
                 <span>Покрытие</span>
                 <strong>{dataStatusQuery.data.coverage_percent != null ? dataStatusQuery.data.coverage_percent + '%' : '100%'}</strong>
             </div>
             <div className="stat">
                 <span>Последнее обновление</span>
                 <strong className="word-stat">{new Date(dataStatusQuery.data.last_updated || Date.now()).toLocaleTimeString()}</strong>
             </div>
           </div>
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
