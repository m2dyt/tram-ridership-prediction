import React, { useState } from "react";
import { explainForecastText } from "../domain/forecast.js";
import Chart from "../components/Chart.jsx";
import {
  Badge,
  Download,
  Empty,
  ErrorBox,
  Loading,
} from "../components/Common.jsx";
import {
  useEvaluations,
  useEvaluation,
  useEvaluationPoints,
} from "../api/hooks";
import {
  date,
  horizonName,
  number,
  seriesKey,
  unitName,
} from "../domain/format.js";
import { spatialLabel } from "../domain/aggregate.js";
import {
  evaluationModelLabel,
  evaluationStatusLabel,
} from "../domain/evaluation.js";
import {
  evaluationScoreRows,
  peakRuleLabel,
} from "../domain/evaluationScores.js";

export default function Evaluations({ caps, route }) {
  const listQuery = useEvaluations({
    dataset_revision_id: caps.dataset_revision_id,
  });
  const list = {
    data: listQuery.data,
    loading: listQuery.isLoading,
    error: listQuery.error,
  };

  const [id, setId] = useState("");
  const selected = id || list.data?.[0]?.id;

  const reportQuery = useEvaluation(selected);
  const report = {
    data: reportQuery.data,
    loading: reportQuery.isLoading,
    error: reportQuery.error,
  };
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">ПРОВЕРКА НА ПРОШЛЫХ ПЕРИОДАХ</p>
          <h2>Качество прогноза</h2>
        </div>
        {report.data && (
          <Badge>{evaluationStatusLabel(report.data.summary.status)}</Badge>
        )}
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
          {report.loading && <Loading />}
          {report.data && (
            <Report key={selected} report={report.data} route={route} />
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
function Report({ report, route }) {
  const [foldId, setFoldId] = useState(report.folds[0]?.id),
    [series, setSeries] = useState("");
  const fold = report.folds.find((f) => f.id === foldId);

  const dataQuery = useEvaluationPoints(
    report.summary.id,
    fold
      ? {
          fold_id: fold.id,
          from: fold.test_start,
          to: fold.test_end,
        }
      : {},
  );
  const data = {
    data: fold ? dataQuery.data : [],
    loading: fold ? dataQuery.isLoading : false,
    error: fold ? dataQuery.error : null,
  };
  const keys = [...new Set((data.data || []).map(seriesKey))];
  const points = (data.data || []).filter(
    (p) => seriesKey(p) === (series || keys[0]),
  );
  return (
    <>
      <p className="notice">
        {evaluationStatusLabel(report.summary.status)}. Проверялась:{" "}
        {evaluationModelLabel(report.summary.model)}. Завершённая проверка сама
        по себе не означает, что модель точнее базового метода.
      </p>
      {report.summary.limitations?.length > 0 && (
        <div className="muted">
          <strong>Ограничения отчёта</strong>
          <ul>
            {report.summary.limitations.map((item, i) => (
              <li key={i}>{explainForecastText(item)}</li>
            ))}
          </ul>
        </div>
      )}
      {report.warnings?.length > 0 && (
        <div className="muted">
          <strong>Условия расчёта</strong>
          <ul>
            {report.warnings.map((item, i) => (
              <li key={i}>{explainForecastText(item)}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Метод</th>
              <th>Маршрут</th>
              <th>Срез</th>
              <th>MAE</th>
              <th>WAPE</th>
              <th>Пар / исключено</th>
            </tr>
          </thead>
          <tbody>
            {evaluationScoreRows(report.scores, route).map((s) => (
              <tr key={`${s.method}-${s.route_id || "all"}-${s.demand_slice}`}>
                <td>{s.methodLabel}</td>
                <td>{s.routeLabel}</td>
                <td>{s.sliceLabel}</td>
                <td>{number(s.mae)}</td>
                <td>
                  {s.wape == null
                    ? s.wape_unavailable_reason || "Нет данных"
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
              <option key={k} value={k}>
                {spatialLabel(
                  JSON.parse(k),
                  JSON.parse(k).route_id === route?.route?.id ? route : null,
                )}
              </option>
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
          fieldLabels={{ model: evaluationModelLabel(report.summary.model) }}
          unit={unitName(report.summary.profile.metric)}
        />
      )}
      <p className="muted">
        Бирюзовый — факт, оранжевый — прогноз проверяемой модели. WAPE считается
        по сумме ошибок, а не среднему процентов.
      </p>
      {report.peak_rule && (
        <p className="muted">Правило пика: {peakRuleLabel(report.peak_rule)}</p>
      )}
    </>
  );
}
