import React, { useState } from "react";
import { Badge, Empty, ErrorBox, Loading } from "../components/Common";
import { date, number, statusName } from "../domain/format";
import { useModels, useModel } from "../api/hooks";

export default function ModelsPage() {
  const modelsQuery = useModels();
  const models = {
    data: modelsQuery.data,
    loading: modelsQuery.isLoading,
    error: modelsQuery.error
  };

  const [selectedId, setSelectedId] = useState("");
  const currentId = selectedId || models.data?.[0]?.id;

  const modelQuery = useModel(currentId);
  const model = {
    data: modelQuery.data,
    loading: modelQuery.isLoading,
    error: modelQuery.error
  };

  return (
    <>
      <div className="mgt-page-hero">
        <div className="mgt-page-hero-content">
          <div className="mgt-page-hero-title">Математическое моделирование и аналитика</div>
          <p className="mgt-page-hero-desc">
            Централизованный реестр прогностических моделей пассажиропотока трамвайной сети ГУП «Мосгортранс». Мониторинг версий, метрик MAE/WAPE и статусов инференса.
          </p>
        </div>
        <div className="mgt-page-hero-badge">Мосгортранс · ML Core</div>
      </div>

      <section className="panel controls">
        <div className="section-heading">
          <div>
            <p className="eyebrow">МАШИННОЕ ОБУЧЕНИЕ</p>
            <h2>ML-Модели</h2>
          </div>
          <Badge>Реестр алгоритмов</Badge>
        </div>
        
        <ErrorBox error={models.error} />
        
        {models.loading ? (
          <Loading />
        ) : models.data?.length > 0 ? (
          <div className="run-selector" style={{ marginTop: '20px' }}>
            <label>
              Доступные модели
              <select
                value={currentId || ""}
                onChange={(e) => setSelectedId(e.target.value)}
              >
                {models.data.map((m) => (
                  <option key={m.id} value={m.id}>
                    Модель {m.version} · {m.method}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="secondary"
              onClick={() => modelsQuery.refetch()}
            >
              Обновить список
            </button>
          </div>
        ) : (
          <Empty>В системе пока нет обученных моделей.</Empty>
        )}
      </section>

      {model.data && (
        <section className="panel" style={{ marginTop: '20px' }}>
          <div className="section-heading">
            <h2>Детали модели: {model.data.version}</h2>
            {model.data.is_active && <Badge tone="primary">Активная (Active)</Badge>}
          </div>
          
          <ErrorBox error={model.error} />
          
          {model.loading ? (
            <Loading />
          ) : (
            <>
              <div className="stat-grid" style={{ marginBottom: '20px' }}>
                <div className="stat">
                  <span>Статус</span>
                  <strong className="word-stat">{statusName(model.data.status)}</strong>
                  <small>Текущее состояние</small>
                </div>
                <div className="stat">
                  <span>Метрика (WAPE)</span>
                  <strong>{model.data.metrics?.overall?.wape != null ? number(model.data.metrics.overall.wape * 100) + '%' : "—"}</strong>
                  <small>Качество на валидации</small>
                </div>
                <div className="stat">
                  <span>Score</span>
                  <strong>{model.data.metrics?.overall?.wape_score != null ? number(model.data.metrics.overall.wape_score) : "—"}</strong>
                  <small>Общий балл</small>
                </div>
              </div>
              
              <div style={{ marginTop: '20px' }}>
                <h3>Паспорт модели (Model Card)</h3>
                <pre style={{ background: 'var(--bg-panel)', padding: '16px', borderRadius: '8px', overflowX: 'auto', whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
                  {model.data.card || "Описание отсутствует"}
                </pre>
              </div>
            </>
          )}
        </section>
      )}
    </>
  );
}
