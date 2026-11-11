import "./map-demand.css";
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Layer,
  Map as NetworkMap,
  NavigationControl,
  Popup,
  Source,
} from "@vis.gl/react-maplibre";
import { useMe } from "../api/hooks";
import { useMapDemand, useDemandNetwork } from "../api/hooks/useMapDemand.js";
import { mapLib } from "../components/mapLib.js";
import { date, number } from "../domain/format.js";
import {
  CARTO_MAP_STYLE,
  FALLBACK_MAP_STYLE,
  shouldFallbackToLocalMapStyle,
} from "../domain/mapStyle.js";
import {
  dayStart,
  demandAt,
  demandBands,
  demandDates,
  demandHours,
  demandIndex,
  demandPlan,
  HOUR,
  localDay,
  MAX_DEMAND_DAYS,
  routeDemandKey,
  stopDemandKey,
} from "../domain/mapDemand.js";

const empty = [];
const dayFormat = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Europe/Moscow",
  day: "numeric",
  month: "long",
  year: "numeric",
});
const elevated = (band) => band === "high" || band === "peak";
const featureCollection = (features) => ({
  type: "FeatureCollection",
  features,
});

function DemandStatus({ item, inline = false }) {
  const band = demandBands[item.band];
  return (
    <div className={inline ? "demand-popup" : "demand-reading"}>
      <span className="demand-band" style={{ "--demand-color": band.color }}>
        {band.label}
      </span>
      <strong>
        {item.value == null
          ? "Нет прогноза"
          : `${number(item.value)} валидаций`}
      </strong>
      {item.mean != null && (
        <small>Среднее за день: {number(item.mean)} в час</small>
      )}
      {item.value != null && item.mean == null && (
        <small>Для сравнения нужен прогноз на все часы дня.</small>
      )}
    </div>
  );
}

export default function MapDemand({ caps }) {
  const bounds = demandDates(caps);
  if (!bounds)
    return (
      <section className="demand-board demand-header">
        <h2>Прогноз нагрузки</h2>
        <p>
          В опубликованных данных нет почасового прогноза посадок или валидаций.
        </p>
      </section>
    );
  return (
    <DemandWorkspace
      key={caps.dataset_revision_id}
      caps={caps}
      bounds={bounds}
    />
  );
}

function DemandWorkspace({ caps, bounds }) {
  const [period, setPeriod] = useState({
    from: bounds.initial,
    to: bounds.initial,
  });
  const [settled, setSettled] = useState(period);
  const [hourIndex, setHourIndex] = useState(8);
  const [focusedRoute, setFocusedRoute] = useState("");
  const [selectedStop, setSelectedStop] = useState("");
  const [showPopup, setShowPopup] = useState(false);
  const [mapStyle, setMapStyle] = useState(CARTO_MAP_STYLE);
  const [mapReady, setMapReady] = useState(false);
  const map = useRef(null);

  useEffect(() => {
    const timer = setTimeout(() => setSettled(period), 400);
    return () => clearTimeout(timer);
  }, [period]);

  const editing = settled !== period;
  const { from, to } = period;
  const hours = useMemo(() => demandHours(from, to), [from, to]);
  const activeHour = hours[Math.min(hourIndex, hours.length - 1)];
  const days = useMemo(
    () => hours.filter((_, i) => i % 24 === 0).map(localDay),
    [hours],
  );
  const network = useDemandNetwork(caps.network_revision_id, days);
  const routes = network.data || empty;
  const [now] = useState(Date.now);
  const session = useMe();
  const plan = useMemo(
    () => (editing ? empty : demandPlan(caps, routes, from, to, now)),
    [caps, editing, routes, from, to, now],
  );
  const result = useMapDemand(plan, session.data);
  const index = demandIndex(result.points);
  const visible = routes.filter(
    ({ route }) =>
      (!focusedRoute || route.id === focusedRoute) &&
      activeHour != null &&
      route.valid_from <= localDay(activeHour) &&
      (!route.valid_to || route.valid_to >= localDay(activeHour)),
  );
  const lines = [];
  const stops = [];
  for (const entry of visible) {
    const routeId = entry.route.id;
    const routeBand = demandAt(index, routeDemandKey(routeId), activeHour).band;
    for (const direction of entry.directions) {
      if (direction.geometry)
        lines.push({
          type: "Feature",
          geometry: direction.geometry,
          properties: { routeId, color: demandBands[routeBand].color },
        });
    }
    for (const stop of entry.stops) {
      if (stop.geometry?.type !== "Point") continue;
      const key = stopDemandKey(routeId, stop.id);
      const demand = demandAt(index, key, activeHour);
      stops.push({
        ...stop,
        key,
        routeNumber: entry.route.number,
        routeId,
        demand,
      });
    }
  }

  const pointFeatures = stops.map(({ key, geometry, demand }) => ({
    type: "Feature",
    geometry,
    properties: { key, color: demandBands[demand.band].color },
  }));
  const stop = stops.find(({ key }) => key === selectedStop);
  const routeReadings = visible.map(({ route }) => ({
    route,
    demand: demandAt(index, routeDemandKey(route.id), activeHour),
  }));
  const hotspots = stops
    .filter(({ demand }) => elevated(demand.band))
    .sort(
      (a, b) => b.demand.value / b.demand.mean - a.demand.value / a.demand.mean,
    );
  const classifiedRoutes = routeReadings.filter(
    ({ demand }) => demand.band !== "unknown",
  ).length;
  const routeReading = routeReadings.find(
    ({ route }) => route.id === focusedRoute,
  );
  const fit = useMemo(() => {
    const coordinates = routes
      .filter(({ route }) => !focusedRoute || route.id === focusedRoute)
      .flatMap(({ stops }) =>
        stops
          .filter((item) => item.geometry?.type === "Point")
          .map(({ geometry }) => geometry.coordinates),
      );
    if (!coordinates.length) return null;
    const xs = coordinates.map(([x]) => x);
    const ys = coordinates.map(([, y]) => y);
    return [
      [Math.min(...xs), Math.min(...ys)],
      [Math.max(...xs), Math.max(...ys)],
    ];
  }, [routes, focusedRoute]);

  useEffect(() => {
    if (fit && mapReady)
      map.current?.fitBounds(fit, { padding: 65, maxZoom: 14.5, duration: 0 });
  }, [fit, mapReady]);

  function changeStart(value) {
    if (!value || value < bounds.min || value > bounds.max) return;
    setPeriod({ from: value, to: demandHours(value, to).length ? to : value });
    setHourIndex(8);
  }

  function changeEnd(value) {
    if (
      !value ||
      value === to ||
      value > bounds.max ||
      !demandHours(from, value).length
    )
      return;
    setPeriod({ from, to: value });
    setHourIndex(8);
  }

  function selectRoute(value) {
    setFocusedRoute(value);
    setSelectedStop("");
    setShowPopup(false);
  }

  function selectStop(key, onMap = false) {
    setSelectedStop(key);
    setShowPopup(Boolean(key));
    if (!onMap && key) {
      const item = stops.find((option) => option.key === key);
      if (item)
        map.current?.easeTo({
          center: item.geometry.coordinates,
          zoom: Math.max(14.5, map.current.getZoom()),
          duration: 0,
        });
    }
  }

  function clickMap(event) {
    const feature = event.features?.[0];
    if (feature?.layer.id === "demand-stops")
      selectStop(feature.properties.key, true);
    else if (feature?.layer.id === "demand-lines")
      selectRoute(feature.properties.routeId);
    else setShowPopup(false);
  }

  const loading =
    editing || network.isLoading || session.isLoading || result.loading;
  const availableDates = dayFormat.formatRange(
    Date.parse(dayStart(bounds.min)),
    Date.parse(dayStart(bounds.max)),
  );
  const maxEnd = localDay(
    Math.min(
      Date.parse(dayStart(bounds.max)),
      Date.parse(dayStart(from)) + (MAX_DEMAND_DAYS - 1) * 24 * HOUR,
    ),
  );

  return (
    <section className="demand-board" aria-labelledby="demand-heading">
      <div className="demand-header">
        <div>
          <h2 id="demand-heading">Прогноз нагрузки</h2>
          <p>
            Выберите даты и час, чтобы увидеть ожидаемый спрос на маршрутах и
            остановках.
          </p>
        </div>
        {caps.source_mode === "demo" && (
          <span className="demand-demo">Демонстрационные данные</span>
        )}
      </div>
      <div className="demand-filters">
        <label>
          Начало периода
          <input
            type="date"
            value={from}
            min={bounds.min}
            max={bounds.max}
            onChange={(e) => changeStart(e.target.value)}
          />
        </label>
        <label>
          Конец периода включительно
          <input
            type="date"
            value={to}
            min={from}
            max={maxEnd}
            onChange={(e) => changeEnd(e.target.value)}
          />
        </label>
        <div className="demand-period-hint">
          <small>Доступные даты: {availableDates}</small>
          <div
            className="demand-presets"
            role="group"
            aria-label="Быстрый выбор периода"
          >
            {[
              [1, "1 день"],
              [3, "3 дня"],
              [7, "Неделя"],
            ].map(([length, label]) => {
              const end = localDay(
                Date.parse(dayStart(from)) + (length - 1) * 24 * HOUR,
              );
              return (
                <button
                  type="button"
                  key={length}
                  className="secondary"
                  disabled={end > maxEnd}
                  aria-pressed={end === to}
                  onClick={() => changeEnd(end)}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="demand-time">
        <div>
          <label htmlFor="demand-hour">Час на карте · Москва</label>
          <output htmlFor="demand-hour">{date(activeHour)}</output>
        </div>
        <input
          id="demand-hour"
          type="range"
          min="0"
          max={hours.length - 1}
          value={Math.min(hourIndex, hours.length - 1)}
          aria-valuetext={date(activeHour)}
          onChange={(e) => setHourIndex(Number(e.target.value))}
        />
      </div>

      <div className="demand-map-key">
        <div className="demand-legend" aria-label="Шкала ожидаемого спроса">
          {Object.entries(demandBands).map(([key, band]) => (
            <span
              key={key}
              className="demand-band"
              style={{ "--demand-color": band.color }}
            >
              {band.label}
            </span>
          ))}
        </div>
        <div className="demand-status" role="status">
          {loading
            ? `Готовим прогноз${result.total ? ` · получено ${result.ready} из ${result.total} расчётов` : "…"}`
            : classifiedRoutes
              ? `Оценка доступна для ${classifiedRoutes} из ${visible.length} маршрутов на карте.`
              : "На выбранный час нет полной оценки нагрузки."}
          {result.unavailable > 0 &&
            " Для запуска новых расчётов войдите как оператор."}
        </div>
      </div>
      <div className="demand-map-grid">
        <div className="demand-canvas">
          <NetworkMap
            ref={map}
            mapLib={mapLib}
            mapStyle={mapStyle}
            style={{ width: "100%", height: "100%" }}
            initialViewState={{
              longitude: 37.6173,
              latitude: 55.7558,
              zoom: 11,
            }}
            interactiveLayerIds={["demand-stops", "demand-lines"]}
            onMouseMove={(event) => {
              event.target.getCanvas().style.cursor = event.features?.length
                ? "pointer"
                : "";
            }}
            onClick={clickMap}
            onLoad={() => setMapReady(true)}
            onError={(event) => {
              if (shouldFallbackToLocalMapStyle(event))
                setMapStyle(FALLBACK_MAP_STYLE);
            }}
          >
            <NavigationControl position="top-right" />
            <Source
              id="demand-routes"
              type="geojson"
              data={featureCollection(lines)}
            >
              <Layer
                id="demand-line-outline"
                type="line"
                layout={{ "line-cap": "round" }}
                paint={{ "line-color": "#ffffff", "line-width": 9 }}
              />
              <Layer
                id="demand-lines"
                type="line"
                layout={{ "line-cap": "round", "line-join": "round" }}
                paint={{ "line-color": ["get", "color"], "line-width": 5 }}
              />
            </Source>
            <Source
              id="demand-points"
              type="geojson"
              data={featureCollection(pointFeatures)}
            >
              <Layer
                id="demand-stops"
                type="circle"
                paint={{
                  "circle-radius": [
                    "case",
                    ["==", ["get", "key"], selectedStop],
                    9,
                    6,
                  ],
                  "circle-color": ["get", "color"],
                  "circle-stroke-width": 2,
                  "circle-stroke-color": "#ffffff",
                }}
              />
            </Source>
            {stop && showPopup && (
              <Popup
                longitude={stop.geometry.coordinates[0]}
                latitude={stop.geometry.coordinates[1]}
                closeOnClick={false}
                onClose={() => setShowPopup(false)}
                offset={10}
                maxWidth="260px"
              >
                <div className="demand-popup">
                  <strong>{stop.name}</strong>
                  <small>
                    Маршрут {stop.routeNumber} · {date(activeHour)}
                  </small>
                  <DemandStatus item={stop.demand} inline />
                </div>
              </Popup>
            )}
          </NetworkMap>
        </div>
        <aside className="demand-inspector" aria-label="Детали нагрузки">
          <h3>Маршруты и остановки</h3>
          <label>
            Маршрут на карте
            <select
              value={focusedRoute}
              onChange={(e) => selectRoute(e.target.value)}
            >
              <option value="">Все маршруты</option>
              {routes.map(({ route }) => (
                <option key={route.id} value={route.id}>
                  {route.number}
                </option>
              ))}
            </select>
          </label>
          {routeReading && <DemandStatus item={routeReading.demand} />}
          <label>
            Остановка
            <select
              value={stop ? selectedStop : ""}
              onChange={(e) => selectStop(e.target.value)}
            >
              <option value="">Выберите остановку</option>
              {stops.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.routeNumber} · {item.name}
                </option>
              ))}
            </select>
          </label>
          {stop ? (
            <>
              <DemandStatus item={stop.demand} />
              {caps.source_mode === "demo" && (
                <small>
                  Спрос по остановкам оценён из общего потока маршрута.
                </small>
              )}
            </>
          ) : (
            <p className="demand-instruction">
              Нажмите на точку карты, чтобы посмотреть прогноз для остановки.
            </p>
          )}
          {hotspots.length > 0 && (
            <div className="demand-hotspots">
              <h4>Остановки с повышенным спросом</h4>
              {hotspots.slice(0, 4).map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => selectStop(item.key)}
                >
                  <span>
                    <span
                      className="demand-band"
                      style={{
                        "--demand-color": demandBands[item.demand.band].color,
                      }}
                    >
                      {item.name}
                    </span>
                    <small>Маршрут {item.routeNumber}</small>
                  </span>
                  <strong>{number(item.demand.value)}</strong>
                </button>
              ))}
            </div>
          )}
        </aside>
      </div>
      <div className="demand-footer">
        <p>
          Цвет сравнивает прогноз на этот час со средним за выбранный день для
          того же маршрута или остановки. Повышенная нагрузка начинается с +20%,
          пиковая — с +50%. Шкала показывает ожидаемые валидации. Данные о
          дорожных заторах в расчёте отсутствуют.
        </p>
        {(result.errors.length > 0 || network.isError || session.isError) && (
          <div className="demand-error" role="alert">
            <span>Часть данных не загрузилась. {result.errors[0]}</span>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                if (network.isError) network.refetch();
                if (session.isError) session.refetch();
                if (plan.length) result.retry();
              }}
            >
              Повторить загрузку
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
