import React from "react";
import { chartSegments, number, date } from "../domain/format.js";
import { Empty } from "./Common.jsx";

export default function Chart({
  points,
  fields = ["value"],
  selected = 0,
  onSelect,
  unit,
}) {
  if (!points.length) return <Empty />;
  const max =
    Math.max(1, ...points.flatMap((p) => fields.map((f) => p[f] ?? 0))) * 1.15;
  const x = (i) => 48 + (i / Math.max(1, points.length - 1)) * 870;
  const y = (v) => 180 - (v / max) * 150;
  const colors = ["#128a85", "#df8f48"];
  return (
    <div className="chart-wrap">
      <svg
        role="img"
        aria-label={`График: ${unit}. Пропуски показаны разрывами линии.`}
        viewBox="0 0 950 215"
        className="chart"
      >
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line
              x1="48"
              x2="920"
              y1={y(max * f)}
              y2={y(max * f)}
              stroke="#e3e9e8"
            />
            <text x="38" y={y(max * f) + 4} textAnchor="end">
              {number(max * f, 0)}
            </text>
          </g>
        ))}
        {fields.map((field, j) =>
          chartSegments(points, field).map((segment, i) => (
            <g key={`${field}-${i}`}>
              <polyline
                points={segment.map(([i, v]) => `${x(i)},${y(v)}`).join(" ")}
                fill="none"
                stroke={colors[j]}
                strokeWidth="2.5"
              />
              {segment.length === 1 && (
                <circle
                  cx={x(segment[0][0])}
                  cy={y(segment[0][1])}
                  r="3"
                  fill={colors[j]}
                />
              )}
            </g>
          )),
        )}
        {onSelect && (
          <line
            x1={x(selected)}
            x2={x(selected)}
            y1="22"
            y2="183"
            stroke="#102b34"
            strokeDasharray="4 4"
          />
        )}
        <text x="48" y="207">
          {date(points[0].interval_start)}
        </text>
        <text x="920" y="207" textAnchor="end">
          {date(points.at(-1).interval_start)}
        </text>
      </svg>
      {onSelect && (
        <label className="timeline">
          Интервал на карте · {date(points[selected]?.interval_start)}
          <input
            aria-label="Интервал на карте"
            type="range"
            min="0"
            max={points.length - 1}
            value={selected}
            onChange={(e) => onSelect(Number(e.target.value))}
          />
        </label>
      )}
      <details>
        <summary>Таблица значений · {points.length} интервалов</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Москва, UTC+3</th>
                {fields.map((f) => (
                  <th key={f}>
                    {f === "actual"
                      ? "Факт"
                      : f === "model"
                        ? "Сезонная база"
                        : unit}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {points.map((p, i) => (
                <tr key={i}>
                  <td>{date(p.interval_start)}</td>
                  {fields.map((f) => (
                    <td key={f}>{number(p[f])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
