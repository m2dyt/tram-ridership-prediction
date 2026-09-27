import React, { useEffect, useState } from "react";
import { date, exportCsv } from "../domain/format.js";
import { useDataStatus } from "../api/hooks";

export function useResource(load, dependencies) {
  const [state, setState] = useState({
    data: null,
    loading: true,
    error: null,
  });
  useEffect(() => {
    const controller = new AbortController();
    setState({ data: null, loading: true, error: null });
    Promise.resolve()
      .then(() => load(controller.signal))
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ data, loading: false, error: null });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({ data: null, loading: false, error });
      });
    return () => controller.abort();
  }, dependencies);
  return state;
}
export function ErrorBox({ error }) {
  if (!error) return null;
  const prefix =
    error.status === 403
      ? "Для этого действия нужен ключ оператора. "
      : error.status === 401
        ? "Ключ доступа не принят. "
        : "";
  return (
    <div role="alert" className="notice error">
      {prefix}
      {error.message}
      {error.requestId && <small>Запрос: {error.requestId}</small>}
    </div>
  );
}
export function Loading() {
  return (
    <div className="empty" role="status">
      Загружаем данные…
    </div>
  );
}
export function Empty({ children }) {
  return (
    <div className="empty">{children || "В этой выборке пока нет данных."}</div>
  );
}
export function Badge({ children, tone = "" }) {
  return <span className={"badge " + tone}>{children}</span>;
}
export function Download({ points, name = "tram-data.csv" }) {
  function save() {
    const url = URL.createObjectURL(
      new Blob([exportCsv(points)], { type: "text/csv;charset=utf-8" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <button className="secondary" onClick={save} disabled={!points?.length}>
      ↓ Скачать CSV
    </button>
  );
}
export function ExternalLink({ url, children }) {
  if (!/^https?:\/\//i.test(url || "")) return <span>{children}</span>;
  return (
    <a href={url} target="_blank" rel="noreferrer">
      {children}
    </a>
  );
}

export function Freshness({ revision }) {
  const statusQuery = useDataStatus();
  
  if (statusQuery.isError) return <ErrorBox error={statusQuery.error} />;
  if (!statusQuery.data || !statusQuery.data.sources) return null;
  const status = { data: statusQuery.data };
  return (
    <details className="freshness-details">
      <summary className="freshness-summary">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="freshness-icon">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </span>
          <span style={{ fontWeight: '600', color: '#1e293b' }}>Свежесть источников данных</span>
          <span className="freshness-time">проверено {date(status.data.checked_at)}</span>
        </div>
        <svg className="freshness-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </summary>
      
      <div className="freshness-body">
        {status.data.dataset_revision_id !== revision ? (
          <p className="notice" style={{ margin: 0 }}>
            Опубликована другая версия данных. Перезагрузите страницу для перехода
            на неё; текущая выборка остаётся закреплённой.
          </p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Источник</th>
                  <th>Последнее событие</th>
                  <th>Загружено</th>
                  <th>Свежесть</th>
                </tr>
              </thead>
              <tbody>
                {status.data.sources.map((s) => (
                  <tr key={s.source}>
                    <td style={{ fontWeight: '600' }}>{s.source}</td>
                    <td>{date(s.event_watermark)}</td>
                    <td>{date(s.ingested_at)}</td>
                    <td>
                      <span className={`status-pill status-${s.freshness}`}>
                        <span className="status-dot"></span>
                        {
                          {
                            fresh: "Актуально",
                            stale: "Устарело",
                            unknown: "Не определена",
                          }[s.freshness] || s.freshness
                        }
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </details>
  );
}
