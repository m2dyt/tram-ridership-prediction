import React, { useMemo, useState } from "react";
import Chart from "../components/Chart.jsx";
import { Download, ErrorBox, Loading } from "../components/Common.jsx";
import { useForecastAggregate } from "../api/hooks";
import { date, number, unitName } from "../domain/format.js";
import {
  endFromInput,
  fromInput,
  groupOptions,
  inputType,
  isTimeGroup,
  lastInput,
  levelSupports,
  perInterval,
  spatialLabel,
  toInput,
} from "../domain/aggregate.js";

export default function ForecastAggregate({ run, route }) {
  const { resolution, spatial_level: level, metric } = run.profile;
  const supports = levelSupports(level);
  const options = groupOptions(resolution, level);
  const initial = {
    from: toInput(run.forecast_start, resolution),
    to: lastInput(run.forecast_end, resolution),
    direction: "",
    stop: "",
    segment: "",
    sectionFrom: "",
    sectionTo: "",
    groupBy: options[1]?.value || "none",
  };
  const [form, setForm] = useState(initial);
  const set = (patch) => setForm((current) => ({ ...current, ...patch }));

  const directions = route.directions || [];
  const namedDirections = directions.filter((d) => d.id);
  const direction = namedDirections.find((d) => d.id === form.direction);
  // Stop positions are unambiguous only inside one direction.
  const line = direction || (directions.length === 1 ? directions[0] : null);
  const scope = line ? [line] : directions;
  const stopNames = Object.fromEntries(
    (route.stops || []).map((s) => [s.id, s.name]),
  );
  const positions = line ? sectionPositions(line, stopNames) : [];
  const stopChoices = line
    ? positions
    : [
        ...new Map(
          scope
            .flatMap((d) => d.stops)
            .map((s) => [
              s.stop_id,
              { value: s.stop_id, label: stopNames[s.stop_id] || s.stop_id },
            ]),
        ).values(),
      ];
  const segmentChoices = scope.flatMap((d) => d.segments || []);
  const sectionOn = Boolean(form.sectionFrom || form.sectionTo);
  const sectionFrom = Number(form.sectionFrom || positions[0]?.sequence);
  const sectionTo = Number(form.sectionTo || positions.at(-1)?.sequence);

  const from = fromInput(form.from, resolution);
  const to = endFromInput(form.to, resolution);
  const periodError =
    from && to && new Date(from) >= new Date(to)
      ? "Начало периода должно быть не позже его конца."
      : sectionOn && sectionFrom > sectionTo
        ? "Первая остановка участка должна идти не позже последней."
        : null;

  const params = useMemo(() => {
    if (!from || !to || periodError) return null;
    const [stopId, sequence] = form.stop.split("|");
    return {
      from,
      to,
      route_id: route.route.id,
      direction_id: form.direction || undefined,
      stop_id: stopId || undefined,
      stop_sequence: sequence || undefined,
      segment_id: form.segment || undefined,
      stop_sequence_from: sectionOn ? sectionFrom : undefined,
      stop_sequence_to: sectionOn ? sectionTo : undefined,
      group_by: form.groupBy,
    };
  }, [
    from,
    to,
    periodError,
    form,
    route.route.id,
    sectionOn,
    sectionFrom,
    sectionTo,
  ]);

  const query = useForecastAggregate(run.id, params);
  const data = query.data;
  const summary = data?.summary;
  const unit = unitName(metric);
  const additive = data?.statistic !== "mean";
  const step = perInterval(resolution);
  const timeGroups = data && isTimeGroup(data.group_by);

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">АГРЕГАЦИЯ ПРОГНОЗА</p>
          <h2>Итоги по участку сети и периоду</h2>
        </div>
        <Download
          points={(data?.groups || []).map((g) => ({
            group: isTimeGroup(data.group_by)
              ? date(g.interval_start)
              : spatialLabel(g, route),
            ...g,
            quality: g.quality.status,
          }))}
          name={`forecast-aggregate-${run.id.slice(0, 8)}.csv`}
        />
      </div>
      <form className="form-grid" onSubmit={(e) => e.preventDefault()}>
        <label>
          Период с
          <input
            required
            type={inputType(resolution)}
            step={resolution === "hour" ? 3600 : undefined}
            value={form.from}
            min={initial.from}
            max={initial.to}
            onChange={(e) => set({ from: e.target.value })}
          />
        </label>
        <label>
          по (включительно)
          <input
            required
            type={inputType(resolution)}
            step={resolution === "hour" ? 3600 : undefined}
            value={form.to}
            min={initial.from}
            max={initial.to}
            onChange={(e) => set({ to: e.target.value })}
          />
        </label>
        <label>
          Направление
          <select
            value={form.direction}
            disabled={!supports.direction || !namedDirections.length}
            onChange={(e) =>
              set({
                direction: e.target.value,
                stop: "",
                segment: "",
                sectionFrom: "",
                sectionTo: "",
              })
            }
          >
            <option value="">
              {namedDirections.length ? "Все направления" : "Одна линия"}
            </option>
            {namedDirections.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        {supports.segment ? (
          <label>
            Участок
            <select
              value={form.segment}
              onChange={(e) => set({ segment: e.target.value })}
            >
              <option value="">Все участки</option>
              {segmentChoices.map((s) => (
                <option key={s.id} value={s.id}>
                  {stopNames[s.from_stop_id] || s.from_stop_id} →{" "}
                  {stopNames[s.to_stop_id] || s.to_stop_id}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <>
            <label>
              Остановка
              <select
                value={form.stop}
                disabled={!supports.stop}
                onChange={(e) =>
                  set({ stop: e.target.value, sectionFrom: "", sectionTo: "" })
                }
              >
                <option value="">Все остановки</option>
                {stopChoices.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            {["sectionFrom", "sectionTo"].map((key) => (
              <label key={key}>
                {key === "sectionFrom" ? "Участок: от" : "до остановки"}
                <select
                  value={form[key]}
                  disabled={!supports.stop || !line}
                  title={
                    supports.stop && !line
                      ? "Позиции остановок различаются по направлениям — выберите направление"
                      : undefined
                  }
                  onChange={(e) => set({ [key]: e.target.value, stop: "" })}
                >
                  <option value="">
                    {key === "sectionFrom"
                      ? "с начала линии"
                      : "до конца линии"}
                  </option>
                  {positions.map((s) => (
                    <option key={s.sequence} value={s.sequence}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </>
        )}
        <label>
          Группировка
          <select
            value={form.groupBy}
            onChange={(e) => set({ groupBy: e.target.value })}
          >
            {options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="secondary"
          onClick={() => setForm(initial)}
        >
          Сбросить
        </button>
      </form>
      {!supports.stop && !supports.segment ? (
        <p className="muted">
          Прогноз рассчитан на уровне маршрута. Для разреза по остановкам и
          участкам выберите горизонт с пометкой «по остановкам».
        </p>
      ) : (
        run.profile.limitations?.length > 0 && (
          <p className="muted">{run.profile.limitations.join(" ")}</p>
        )
      )}
      {periodError && <div className="notice error">{periodError}</div>}
      <ErrorBox error={query.error} />
      {query.isLoading && !data ? (
        <Loading />
      ) : summary ? (
        <>
          <div className="stat-grid">
            <div className="stat">
              <span>{additive ? "Итого за период" : "Среднее за период"}</span>
              <strong>{number(summary.value, 0)}</strong>
              <small>
                {unit} · {date(data.from)} — {date(data.to)}
              </small>
            </div>
            <div className="stat">
              <span>В среднем за {step}</span>
              <strong>{number(summary.interval_mean)}</strong>
              <small>
                {unit}, {summary.interval_count} интервалов
              </small>
            </div>
            <div className="stat">
              <span>Пиковый {step}</span>
              <strong>{number(summary.interval_max, 0)}</strong>
              <small>
                {summary.peak_interval_start
                  ? date(summary.peak_interval_start)
                  : "нет значений"}
              </small>
            </div>
            <div className="stat">
              <span>Покрытие выборки</span>
              <strong>
                {summary.point_count - summary.missing_count}
                <em> / {summary.point_count}</em>
              </strong>
              <small>
                точек прогноза · рядов: {summary.series_count}
                {summary.missing_count ? " · пропуски не считаются нулём" : ""}
              </small>
            </div>
          </div>
          {timeGroups && data.groups.length > 0 && (
            <Chart points={data.groups} unit={unit} />
          )}
          {!timeGroups && data.groups.length > 0 && (
            <GroupTable
              groups={data.groups}
              route={route}
              total={additive ? summary.value : null}
              unit={unit}
            />
          )}
        </>
      ) : null}
    </section>
  );
}

function GroupTable({ groups, route, total, unit }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Группа</th>
            <th>
              {total != null ? "Итого" : "Среднее"}, {unit}
            </th>
            {total != null && <th>Доля</th>}
            <th>Пик</th>
            <th>Покрытие</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((g, i) => (
            <tr key={i}>
              <td>{spatialLabel(g, route)}</td>
              <td>{number(g.value, 0)}</td>
              {total != null && (
                <td>
                  {total && g.value != null
                    ? number((g.value / total) * 100) + "%"
                    : "—"}
                </td>
              )}
              <td>
                {number(g.interval_max, 0)} ·{" "}
                {g.peak_interval_start ? date(g.peak_interval_start) : "—"}
              </td>
              <td>
                {g.quality.coverage_ratio == null
                  ? "—"
                  : number(g.quality.coverage_ratio * 100) + "%"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function sectionPositions(line, stopNames) {
  return [...line.stops]
    .sort((a, b) => a.sequence - b.sequence)
    .map((s) => ({
      value: `${s.stop_id}|${s.sequence}`,
      sequence: s.sequence,
      label: `${s.sequence}. ${stopNames[s.stop_id] || s.stop_id}`,
    }));
}
