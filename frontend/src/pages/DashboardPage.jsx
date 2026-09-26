import React from "react";
import Chart from "../components/Chart";

export default function DashboardPage({ caps }) {
  // Mock data for the dashboard chart
  const dashboardPoints = [
    { interval_start: "2026-09-26T06:00:00Z", value: 1200 },
    { interval_start: "2026-09-26T07:00:00Z", value: 3500 },
    { interval_start: "2026-09-26T08:00:00Z", value: 8900 },
    { interval_start: "2026-09-26T09:00:00Z", value: 6500 },
    { interval_start: "2026-09-26T10:00:00Z", value: 4200 },
    { interval_start: "2026-09-26T11:00:00Z", value: 3800 },
    { interval_start: "2026-09-26T12:00:00Z", value: 4100 },
    { interval_start: "2026-09-26T13:00:00Z", value: 4500 },
    { interval_start: "2026-09-26T14:00:00Z", value: 5000 },
    { interval_start: "2026-09-26T15:00:00Z", value: 5400 },
    { interval_start: "2026-09-26T16:00:00Z", value: 7100 },
    { interval_start: "2026-09-26T17:00:00Z", value: 9200 },
    { interval_start: "2026-09-26T18:00:00Z", value: 8400 },
    { interval_start: "2026-09-26T19:00:00Z", value: 5300 },
  ];

  return (
    <div className="panel">
       <div className="stat-grid">
           <div className="stat">
               <span>Используемая модель</span>
               <strong className="word-stat">{caps?.capabilities?.some_model_name || "Трамвай ПРОГНОЗ v1"}</strong>
           </div>
           <div className="stat">
               <span>Ревизия сети</span>
               <strong className="word-stat">{caps?.network_revision_id || "Нет данных"}</strong>
           </div>
           <div className="stat">
               <span>Режим данных</span>
               <strong className="word-stat">{caps?.source_mode || "Реальный"}</strong>
           </div>
           <div className="stat">
               <span>Прогнозируемых маршрутов</span>
               <strong className="word-stat">39</strong>
           </div>
       </div>

       <div className="panel" style={{ marginTop: '2rem', marginBottom: '2rem' }}>
          <h2>Общий пассажиропоток (факт + прогноз)</h2>
          <p className="muted">Динамика по всей сети маршрутов за текущие сутки.</p>
          <div style={{ marginTop: '20px' }}>
              <Chart points={dashboardPoints} fields={["value"]} unit="пасс." />
          </div>
       </div>
    </div>
  );
}
