import React, { useState } from "react";
import { ErrorBox } from "../components/Common.jsx";
import { number } from "../domain/format.js";

export default function Fleet({ api }) {
  const [values, setValues] = useState({
    passengers_per_hour: 1000,
    vehicle_capacity: 100,
    target_ratio: 0.8,
    round_trip_minutes: 60,
    current_vehicles: 10,
    reserve_vehicles: 2,
  });
  const [result, setResult] = useState(null),
    [error, setError] = useState(null),
    [busy, setBusy] = useState(false);
  const fields = [
    [
      "passengers_per_hour",
      "Поток на загруженном участке, чел/час",
      0,
      1000000,
    ],
    ["vehicle_capacity", "Вместимость одного вагона", 1, 10000],
    ["target_ratio", "Целевая доля заполнения", 0.01, 1],
    ["round_trip_minutes", "Полный оборот с отстоем, мин", 1, 1440],
    ["current_vehicles", "Вагонов сейчас", 0, 10000],
    ["reserve_vehicles", "Доступный резерв", 0, 10000],
  ];
  async function submit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      setResult(await api.request("/scenarios/fleet", { body: values }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>Сценарий выпуска</h2>
        <span className="badge amber">Заданные допущения</span>
      </div>
      <p className="notice">
        Используйте поток через наиболее загруженный участок одного направления,
        а не сумму посадок по маршруту. Расчёт предполагает равномерное движение
        одинаковых вагонов. Изменения в расписание не вносятся.
      </p>
      <form onSubmit={submit} className="form-grid">
        {fields.map(([key, label, min, max]) => (
          <label key={key}>
            {label}
            <input
              required
              type="number"
              min={min}
              max={max}
              step={key === "target_ratio" ? "0.01" : "1"}
              value={values[key]}
              onChange={(e) => {
                setValues({
                  ...values,
                  [key]: e.target.value === "" ? "" : Number(e.target.value),
                });
                setResult(null);
              }}
            />
          </label>
        ))}
        <button disabled={busy}>Рассчитать сценарий</button>
      </form>
      <ErrorBox error={error} />
      {result && (
        <div className="stat-grid" style={{ marginTop: 22 }}>
          <div className="stat">
            <span>Требуется вагонов</span>
            <strong>{result.required_vehicles}</strong>
            <small>Дополнительно: {result.additional_vehicles}</small>
          </div>
          <div className="stat">
            <span>Максимальный интервал</span>
            <strong>
              {result.maximum_headway_minutes == null
                ? "—"
                : number(result.maximum_headway_minutes) + " мин"}
            </strong>
            <small>При заданном целевом заполнении</small>
          </div>
          <div className="stat">
            <span>Достаточность резерва</span>
            <strong className="word-stat">
              {result.feasible_with_reserve
                ? "Достаточно"
                : "Не хватает: " + result.reserve_shortfall}
            </strong>
            <small>Доступно с резервом: {result.available_vehicles}</small>
          </div>
        </div>
      )}
    </section>
  );
}
