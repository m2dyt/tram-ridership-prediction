import React, { useState } from "react";
import Fleet from "./Fleet.jsx";
import ForecastLoad from "./ForecastLoad.jsx";
import {
  Badge,
  Empty,
  ErrorBox,
  Loading,
} from "../components/Common.jsx";
import { useOccupancyTrips, useOccupancyEvents, useCreateOccupancyTrip, useApplyOccupancyEvent } from "../api/hooks";
import {
  date,
  localInput,
  moscowTime,
  number,
  statusName,
} from "../domain/format.js";

export default function Occupancy({ caps, route }) {
  const [id, setId] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  
  const listQuery = useOccupancyTrips();
  const list = {
    data: listQuery.data,
    loading: listQuery.isLoading,
    error: listQuery.error
  };
  const trips = (list.data || []).filter(
    (t) =>
      t.plan.network_revision_id === caps.network_revision_id &&
      t.plan.route_id === route.route.id,
  );
  const selected = trips.find((t) => t.id === id) || trips[0];
  
  const eventsQuery = useOccupancyEvents(selected?.id);
  const events = {
    data: eventsQuery.data,
    loading: eventsQuery.isLoading,
    error: eventsQuery.error
  };
  const [direction, setDirection] = useState(route.directions[0]?.id),
    [strategy, setStrategy] = useState("uniform"),
    [capacity, setCapacity] = useState("100"),
    [initial, setInitial] = useState("0"),
    [vehicle, setVehicle] = useState("vehicle-01");
  const [started, setStarted] = useState(
    localInput(new Date(Date.now() - 3600000).toISOString()),
  );
  const createMutation = useCreateOccupancyTrip();

  async function create(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const dir = route.directions.find((d) => d.id === direction),
        start = new Date(moscowTime(started));
      const plan = {
        trip_id: crypto.randomUUID(),
        vehicle_id: vehicle,
        network_revision_id: caps.network_revision_id,
        route_id: route.route.id,
        direction_id: dir.id,
        source_mode: caps.source_mode,
        started_at: start.toISOString(),
        strategy,
        capacity: capacity === "" ? null : Number(capacity),
        initial_passengers: Number(initial),
        terminal_clear: true,
        stops: dir.stops.map((s, i) => ({
          ...s,
          arrival_at: new Date(
            start.getTime() + (i + 1) * 5 * 60000,
          ).toISOString(),
        })),
      };
      const result = await createMutation.mutateAsync(plan);
      setId(result.id);
      listQuery.refetch();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <ForecastLoad caps={caps} route={route} />
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">СОХРАНЕНИЕ ОСТАТКА МЕЖДУ ОСТАНОВКАМИ</p>
            <h2>Наполненность вагона</h2>
          </div>
          <Badge tone="amber">Расчётная оценка</Badge>
        </div>
        <p className="muted">
          Посадки − высадки + остаток с прошлого участка. Оценка может быть
          дробной: это ожидаемое число пассажиров. Вместимость не обрезает
          переполнение.
        </p>
        <details>
          <summary>Создать рейс для ручного сценария</summary>
          <p className="notice">
            Форма задаёт интервал 5 минут между остановками. Для фактического
            расписания передайте точные arrival_at через API или replay-trip.
          </p>
          <form className="form-grid" onSubmit={create}>
            <label>
              Вагон
              <input
                required
                pattern="[A-Za-z0-9_.:-]+"
                maxLength="128"
                value={vehicle}
                onChange={(e) => setVehicle(e.target.value)}
              />
            </label>
            <label>
              Направление
              <select
                value={direction}
                onChange={(e) => setDirection(e.target.value)}
              >
                {route.directions.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Начало, Москва
              <input
                required
                type="datetime-local"
                value={started}
                onChange={(e) => setStarted(e.target.value)}
              />
            </label>
            <label>
              Сценарий
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
              >
                <option value="short">До следующей остановки</option>
                <option value="uniform">Равномерно по времени</option>
                <option value="long">До конечной</option>
              </select>
            </label>
            <label>
              Вместимость
              <input
                type="number"
                min="1"
                step="1"
                value={capacity}
                onChange={(e) => setCapacity(e.target.value)}
                placeholder="Неизвестна"
              />
            </label>
            <label>
              Пассажиров в начале
              <input
                required
                type="number"
                min="0"
                step="any"
                value={initial}
                onChange={(e) => setInitial(e.target.value)}
              />
            </label>
            <button disabled={busy}>
              {busy ? "Создаём…" : "Создать рейс"}
            </button>
          </form>
        </details>
        <ErrorBox error={error || list.error} />
        <div className="toolbar">
          <label>
            Рейс
            <select
              value={selected?.id || ""}
              onChange={(e) => setId(e.target.value)}
            >
              <option value="" disabled>
                Выберите рейс
              </option>
              {trips.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.plan.vehicle_id} · {statusName(t.state.status)} ·{" "}
                  {t.id.slice(0, 12)}
                </option>
              ))}
            </select>
          </label>
          <button
            className="secondary"
            onClick={() => listQuery.refetch()}
          >
            Обновить
          </button>
        </div>
        {list.loading ? (
          <Loading />
        ) : selected ? (
          <Trip
            key={selected.id + ":" + selected.state.version}
            trip={selected}
            events={events}
            onUpdate={() => { listQuery.refetch(); eventsQuery.refetch(); }}
          />
        ) : (
          <Empty>Для маршрута пока нет рейсов.</Empty>
        )}
      </section>
      <Fleet />
    </>
  );
}

function Trip({ trip, events, onUpdate }) {
  const next = trip.plan.stops[trip.state.next_stop_index];
  const [boardings, setBoardings] = useState("0"),
    [observed, setObserved] = useState(""),
    [at, setAt] = useState(localInput(next?.arrival_at)),
    [error, setError] = useState(null),
    [busy, setBusy] = useState(false);

  const applyEventMutation = useApplyOccupancyEvent(trip.id);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await applyEventMutation.mutateAsync({
        event_id: `visit-${next.sequence}`,
        sequence: next.sequence,
        occurred_at: moscowTime(at),
        available_at: new Date().toISOString(),
        boardings: Number(boardings),
        observed_alightings: observed === "" ? null : Number(observed),
      });
      onUpdate();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="stat-grid">
        <div className="stat">
          <span>Осталось в вагоне</span>
          <strong>{number(trip.state.remaining)}</strong>
          <small>пассажиров · оценка</small>
        </div>
        <div className="stat">
          <span>От вместимости</span>
          <strong>
            {trip.state.occupancy_ratio == null
              ? "—"
              : number(trip.state.occupancy_ratio * 100) + " %"}
          </strong>
          <small>
            {trip.state.flags.includes("over_capacity")
              ? "Превышение вместимости"
              : "Вместимость: " + number(trip.plan.capacity)}
          </small>
        </div>
        <div className="stat">
          <span>Состояние рейса</span>
          <strong className="word-stat">{statusName(trip.state.status)}</strong>
          <small>Обработано остановок: {trip.state.version}</small>
        </div>
      </div>
      {next && (
        <form onSubmit={submit} className="form-grid">
          <label>
            Следующая остановка
            <input disabled value={`${next.sequence} · ${next.stop_id}`} />
          </label>
          <label>
            Прибытие, Москва
            <input
              required
              type="datetime-local"
              value={at}
              onChange={(e) => setAt(e.target.value)}
            />
          </label>
          <label>
            Вошло
            <input
              required
              type="number"
              min="0"
              step="any"
              value={boardings}
              onChange={(e) => setBoardings(e.target.value)}
            />
          </label>
          <label>
            Вышло по измерению
            <input
              type="number"
              min="0"
              step="any"
              placeholder="Пусто = оценить"
              value={observed}
              onChange={(e) => setObserved(e.target.value)}
            />
          </label>
          <button disabled={busy}>
            {busy ? "Сохраняем…" : "Обработать остановку"}
          </button>
        </form>
      )}
      <ErrorBox error={error || events.error} />
      <h3>Журнал баланса</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Остановка</th>
              <th>Время</th>
              <th>Вошло</th>
              <th>Вышло</th>
              <th>Остаток</th>
              <th>Высадка</th>
            </tr>
          </thead>
          <tbody>
            {events.data?.items.map(({ event, state_after: s }) => (
              <tr key={event.event_id}>
                <td>{event.sequence}</td>
                <td>{date(event.occurred_at)}</td>
                <td>{number(event.boardings)}</td>
                <td>{number(s.last_exchange.alightings)}</td>
                <td>{number(s.remaining)}</td>
                <td>
                  {s.last_exchange.alightings_kind === "observed"
                    ? "Измерение"
                    : "Оценка"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
