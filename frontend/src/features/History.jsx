import React, { useEffect, useState } from "react";
import Chart from "../components/Chart.jsx";
import { Download, Empty, ErrorBox, Loading } from "../components/Common.jsx";
import {
  localInput,
  moscowTime,
  seriesKey,
  unitName,
} from "../domain/format.js";
import { useObservations } from "../api/hooks";
import { levelName, spatialLabel } from "../domain/aggregate.js";
import { initialHistoryWindow } from "../domain/historyWindow.js";

export default function History({ caps, route }) {
  const profiles = caps.observation_profiles.filter((p) =>
    p.route_ids.includes(route.route.id),
  );
  const [id, setId] = useState(profiles[0]?.id),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [query, setQuery] = useState(null),
    [series, setSeries] = useState("");
  const profile = profiles.find((p) => p.id === id) || profiles[0];
  useEffect(() => {
    if (!profile) return;
    const window = initialHistoryWindow(profile);
    setFrom(localInput(window.from));
    setTo(localInput(window.to));
    setQuery(null);
    setSeries("");
  }, [profile?.id]);
  const resultQuery = useObservations(query);
  const result = {
    data: resultQuery.data,
    loading: resultQuery.isLoading,
    error: resultQuery.error,
  };
  const keys = [...new Set((result.data || []).map(seriesKey))];
  const points = (result.data || []).filter(
    (p) => seriesKey(p) === (series || keys[0]),
  );
  if (!profile) return <Empty />;
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">ВЕРСИОНИРОВАННЫЕ ДАННЫЕ</p>
          <h2>История наблюдений</h2>
        </div>
        <Download points={points} />
      </div>
      <form
        className="form-grid"
        onSubmit={(e) => {
          e.preventDefault();
          setSeries("");
          setQuery({
            dataset_revision_id: caps.dataset_revision_id,
            observation_profile_id: profile.id,
            route_id: route.route.id,
            from: moscowTime(from),
            to: moscowTime(to),
          });
        }}
      >
        <label>
          Профиль
          <select value={profile.id} onChange={(e) => setId(e.target.value)}>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {unitName(p.metric)} ·{" "}
                {{ hour: "по часам", day: "по дням", month: "по месяцам" }[
                  p.resolution
                ] || p.resolution}
                {levelName(p.spatial_level)}
              </option>
            ))}
          </select>
        </label>
        <label>
          От, Москва
          <input
            required
            type="datetime-local"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </label>
        <label>
          До, не включительно
          <input
            required
            type="datetime-local"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </label>
        <button>Показать историю</button>
      </form>
      <ErrorBox error={result.error} />
      {result.loading && query ? (
        <Loading />
      ) : result.data ? (
        <>
          {keys.length > 1 && (
            <label>
              Пространственный ряд
              <select
                value={series || keys[0]}
                onChange={(e) => setSeries(e.target.value)}
              >
                {keys.map((k) => (
                  <option key={k} value={k}>
                    {spatialLabel(JSON.parse(k), route)}
                  </option>
                ))}
              </select>
            </label>
          )}
          <Chart points={points} unit={unitName(profile.metric)} />
          <p className="muted">
            Пропуски остаются пропусками. Наблюдения и восстановленные значения
            различаются в API по value_kind.
          </p>
        </>
      ) : (
        <Empty>Выберите период до 366 дней и загрузите историю.</Empty>
      )}
    </section>
  );
}
