import React, { useEffect, useState } from "react";
import { date, exportCsv } from "../domain/format.js";

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

export function Freshness({ api, revision }) {
  const [tick, setTick] = useState(0);
  const status = useResource(
    (signal) => api.request("/data-status", { signal }),
    [api, tick],
  );
  useEffect(() => {
    const timer = setInterval(() => setTick((v) => v + 1), 30000);
    return () => clearInterval(timer);
  }, []);
  if (status.error) return <ErrorBox error={status.error} />;
  if (!status.data) return null;
  return (
    <details>
      <summary>
        Свежесть источников · проверено {date(status.data.checked_at)}
      </summary>
      {status.data.dataset_revision_id !== revision ? (
        <p className="notice">
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
                  <td>{s.source}</td>
                  <td>{date(s.event_watermark)}</td>
                  <td>{date(s.ingested_at)}</td>
                  <td>
                    {
                      {
                        fresh: "Актуально",
                        stale: "Устарело",
                        unknown: "Не определена",
                      }[s.freshness]
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}
