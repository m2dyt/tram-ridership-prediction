import React, { useState } from "react";
import Map from "../components/Map.jsx";
import {
  Badge,
  Empty,
  ErrorBox,
  ExternalLink,
  Loading,
  useResource,
} from "../components/Common.jsx";
import { date, number, statusName } from "../domain/format.js";

export default function Context({ api, route }) {
  const [revision, setRevision] = useState(0),
    [provider, setProvider] = useState("open-meteo"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(null),
    [id, setId] = useState("");
  const list = useResource(
    (signal) => api.all("/context/snapshots", {}, signal),
    [api, revision],
  );
  const selected = id || list.data?.[0]?.id;
  const detail = useResource(
    (signal) =>
      selected
        ? api.request("/context/snapshots/" + selected, { signal })
        : null,
    [api, selected],
  );
  async function refresh() {
    setBusy(true);
    setError(null);
    try {
      const now = new Date(),
        xy = route.stops.find((s) => s.geometry)?.geometry.coordinates || [
          37.62, 55.75,
        ];
      const snap = await api.request("/context/refresh", {
        body: {
          provider,
          latitude: xy[1],
          longitude: xy[0],
          from: now.toISOString(),
          to: new Date(now.getTime() + 2 * 86400000).toISOString(),
        },
      });
      setId(snap.id);
      setRevision((v) => v + 1);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const snap = detail.data;
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">ПОГОДА · МЕРОПРИЯТИЯ · ПЕРЕСАДКИ</p>
          <h2>Городской контекст</h2>
        </div>
        <Badge>Снимки источников</Badge>
      </div>
      <p className="muted">
        Эти признаки подготовлены для будущей модели. Сезонная база пока не
        меняет прогноз из-за погоды или мероприятий.
      </p>
      <div className="toolbar">
        <label>
          Источник
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          >
            <option value="open-meteo">Open-Meteo · погода</option>
            <option value="weatherapi">WeatherAPI · нужен ключ</option>
            <option value="kudago">KudaGo · мероприятия Москвы</option>
            <option value="timepad">Timepad · мероприятия Москвы</option>
          </select>
        </label>
        <button disabled={busy} onClick={refresh}>
          {busy ? "Получаем снимок…" : "Получить свежие данные"}
        </button>
      </div>
      <ErrorBox error={error || list.error || detail.error} />
      {list.loading ? (
        <Loading />
      ) : list.data?.length ? (
        <>
          <label>
            Сохранённый снимок
            <select value={selected} onChange={(e) => setId(e.target.value)}>
              {list.data.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.provider} · {date(s.created_at)} · {statusName(s.status)}
                </option>
              ))}
            </select>
          </label>
          {snap && (
            <>
              <div className="context-meta">
                <Badge tone={snap.status === "unavailable" ? "amber" : ""}>
                  {statusName(snap.status)}
                </Badge>
                <span>
                  {snap.record_count} записей · доступны с{" "}
                  {date(snap.available_at)}
                </span>
                <ExternalLink url={snap.source_url}>
                  {snap.attribution}
                </ExternalLink>
              </div>
              {snap.warnings.map((w, i) => (
                <p className="muted" key={i}>
                  {w}
                </p>
              ))}
              {snap.kind !== "weather" && (
                <Map route={route} context={snap.records} />
              )}
              {snap.records.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        {snap.kind === "weather" ? (
                          <>
                            <th>Время, Москва</th>
                            <th>°C</th>
                            <th>Осадки, мм</th>
                            <th>Ветер, км/ч</th>
                          </>
                        ) : (
                          <>
                            <th>Объект</th>
                            <th>Начало / категория</th>
                            <th>Координаты</th>
                          </>
                        )}
                      </tr>
                    </thead>
                    <tbody>
                      {snap.records.map((r, i) => (
                        <tr key={i}>
                          {snap.kind === "weather" ? (
                            <>
                              <td>{date(r.time)}</td>
                              <td>{number(r.temperature_c)}</td>
                              <td>{number(r.precipitation_mm)}</td>
                              <td>{number(r.wind_kmh)}</td>
                            </>
                          ) : (
                            <>
                              <td>
                                <ExternalLink url={r.source_url}>
                                  {r.title}
                                </ExternalLink>
                              </td>
                              <td>{r.start ? date(r.start) : r.category}</td>
                              <td>
                                {r.coordinates?.join(", ") || "Не указаны"}
                              </td>
                            </>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty>
                  Источник не предоставил записей. Причина указана выше.
                </Empty>
              )}
            </>
          )}
        </>
      ) : (
        <Empty>
          Получите первый снимок. Геоданные Москвы импортируются командой
          import-geo.
        </Empty>
      )}
    </section>
  );
}
