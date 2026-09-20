import React, { useState } from "react";
import Chart from "../components/Chart.jsx";
import {
  Badge,
  Download,
  Empty,
  ErrorBox,
  Loading,
  useResource,
} from "../components/Common.jsx";
import {
  date,
  horizonName,
  number,
  seriesKey,
  unitName,
} from "../domain/format.js";

export default function Evaluations({ api, caps }) {
  const list = useResource(
    (signal) =>
      api.all(
        "/evaluations",
        { dataset_revision_id: caps.dataset_revision_id },
        signal,
      ),
    [api, caps.dataset_revision_id],
  );
  const [id, setId] = useState("");
  const selected = id || list.data?.[0]?.id;
  const report = useResource(
    (signal) =>
      selected ? api.request("/evaluations/" + selected, { signal }) : null,
    [api, selected],
  );
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">ПРОВЕРКА НА ПРОШЛЫХ ПЕРИОДАХ</p>
          <h2>Качество прогноза</h2>
        </div>
        <Badge>Без обучения</Badge>
      </div>
      <ErrorBox error={list.error || report.error} />
      {list.loading ? (
        <Loading />
      ) : list.data?.length ? (
        <>
          <label>
            Отчёт
            <select value={selected} onChange={(e) => setId(e.target.value)}>
              {list.data.map((r) => (
                <option key={r.id} value={r.id}>
                  {horizonName(r.profile.horizon)} · {date(r.created_at)} ·{" "}
                  {r.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          {report.data && (
            <Report key={selected} api={api} report={report.data} />
          )}
        </>
      ) : (
        <Empty>
          Отчётов пока нет. Их создаёт команда evaluate; инструкция находится в
          документации проекта.
        </Empty>
      )}
    </section>
  );
}
function Report({ api, report }) {
  const [foldId, setFoldId] = useState(report.folds[0]?.id),
    [series, setSeries] = useState("");
  const fold = report.folds.find((f) => f.id === foldId);
  const data = useResource(
    (signal) =>
      fold
        ? api.all(
            `/evaluations/${report.summary.id}/points`,
            { fold_id: fold.id, from: fold.test_start, to: fold.test_end },
            signal,
          )
        : [],
    [api, report.summary.id, foldId],
  );
  const keys = [...new Set((data.data || []).map(seriesKey))];
  const points = (data.data || []).filter(
    (p) => seriesKey(p) === (series || keys[0]),
  );
  return (
    <>
      <p className="notice">
        Сейчас оценивается сезонная база. Значения model и seasonal_naive
        совпадают. Точность обученной модели ещё не измерялась.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Срез</th>
              <th>MAE</th>
              <th>WAPE</th>
              <th>Пар / исключено</th>
            </tr>
          </thead>
          <tbody>
            {report.scores
              .filter((s) => s.method === "model" && s.route_id === null)
              .map((s) => (
                <tr key={s.demand_slice}>
                  <td>
                    {s.demand_slice === "all" ? "Все интервалы" : "Часы пик"}
                  </td>
                  <td>{number(s.mae)}</td>
                  <td>
                    {s.wape == null
                      ? "Нет данных"
                      : number(s.wape * 100) + " %"}
                  </td>
                  <td>
                    {s.sample_count} / {s.excluded_count}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      {report.folds.length > 0 && (
        <div className="toolbar">
          <label>
            Срез времени
            <select
              value={foldId}
              onChange={(e) => {
                setFoldId(e.target.value);
                setSeries("");
              }}
            >
              {report.folds.map((f) => (
                <option key={f.id} value={f.id}>
                  {date(f.test_start)} → {date(f.test_end)}
                </option>
              ))}
            </select>
          </label>
          <Download points={points} />
        </div>
      )}
      {keys.length > 1 && (
        <label>
          Пространственный ряд
          <select
            value={series || keys[0]}
            onChange={(e) => setSeries(e.target.value)}
          >
            {keys.map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
        </label>
      )}
      <ErrorBox error={data.error} />
      {data.loading ? (
        <Loading />
      ) : (
        <Chart
          points={points}
          fields={["actual", "model"]}
          unit={unitName(report.summary.profile.metric)}
        />
      )}
      <p className="muted">
        Бирюзовый — факт, оранжевый — сезонная база. Пик: 07–09 и 17–19 по
        Москве, только для часовых данных. WAPE считается по сумме ошибок, а не
        среднему процентов.
      </p>
    </>
  );
}
