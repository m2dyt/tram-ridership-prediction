import React, { useEffect, useRef } from "react";
import L from "leaflet";
import { number } from "../domain/format.js";

const EMPTY_CONTEXT = [];

export default function Map({ route, forecast, context = EMPTY_CONTEXT }) {
  const root = useRef(),
    map = useRef(),
    layers = useRef();
  useEffect(() => {
    map.current = L.map(root.current, { scrollWheelZoom: false }).setView(
      [55.757, 37.628],
      13,
    );
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map.current);
    layers.current = L.featureGroup().addTo(map.current);
    const observer = new ResizeObserver(() => map.current?.invalidateSize());
    observer.observe(root.current);
    return () => {
      observer.disconnect();
      map.current.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    const group = layers.current;
    group.clearLayers();
    const popup = (title, detail) => {
      const el = document.createElement("div");
      const b = document.createElement("strong");
      b.textContent = title;
      el.append(
        b,
        document.createElement("br"),
        document.createTextNode(detail),
      );
      return el;
    };
    route?.directions?.forEach((d) => {
      if (d.geometry)
        L.geoJSON(d.geometry, {
          style: { color: "#95b6b3", weight: 6, opacity: 0.7 },
        }).addTo(group);
    });
    route?.stops?.forEach((s) => {
      if (s.geometry)
        L.circleMarker([...s.geometry.coordinates].reverse(), {
          radius: 5,
          color: "#102b34",
          fillColor: "#fff",
          fillOpacity: 1,
          weight: 2,
        })
          .bindPopup(popup(s.name, s.id))
          .addTo(group);
    });
    forecast?.features?.forEach((f) => {
      if (f.geometry)
        L.geoJSON(f, {
          style: {
            color: f.properties.value == null ? "#999" : "#128a85",
            weight: 7,
          },
          pointToLayer: (f, latlng) =>
            L.circleMarker(latlng, { radius: 8, color: "#128a85" }),
        })
          .bindPopup(popup("Прогноз", number(f.properties.value)))
          .addTo(group);
    });
    context.forEach((p) => {
      if (p.coordinates)
        L.circleMarker([...p.coordinates].reverse(), {
          radius: 6,
          color: "#cc7a32",
          fillOpacity: 0.75,
        })
          .bindPopup(popup(p.title, p.category || "Мероприятие"))
          .addTo(group);
    });
    if (group.getLayers().length && group.getBounds().isValid())
      map.current.fitBounds(group.getBounds(), {
        padding: [35, 35],
        maxZoom: 14,
      });
  }, [route, forecast, context]);
  return (
    <div className="map-shell">
      <div
        ref={root}
        className="map"
        aria-label="Карта маршрута OpenStreetMap"
      />
      <div className="map-key">
        <i /> Маршрут <i className="dot" /> Остановка <i className="orange" />{" "}
        Объект города
      </div>
    </div>
  );
}
