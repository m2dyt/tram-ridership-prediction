import React, { useMemo } from "react";
import MapLibreMap, { Source, Layer } from "@vis.gl/react-maplibre";
import { number } from "../domain/format.js";

const EMPTY_CONTEXT = [];

export default function Map({ route, forecast, context = EMPTY_CONTEXT }) {
  // Конвертируем маршруты в GeoJSON для отрисовки линий
  const routeFeatures = useMemo(() => {
    const features = [];
    route?.directions?.forEach((d) => {
      if (d.geometry) {
        features.push({
          type: "Feature",
          geometry: d.geometry,
          properties: { id: d.id || Math.random().toString() },
        });
      }
    });
    return { type: "FeatureCollection", features };
  }, [route]);

  // Конвертируем остановки в GeoJSON для отрисовки точек
  const stopFeatures = useMemo(() => {
    const features = [];
    route?.stops?.forEach((s) => {
      if (s.geometry) {
        features.push({
          type: "Feature",
          geometry: s.geometry,
          properties: { name: s.name, id: s.id },
        });
      }
    });
    return { type: "FeatureCollection", features };
  }, [route]);

  return (
    <div className="map-shell" style={{ height: "400px", width: "100%", position: "relative" }}>
      <MapLibreMap
        initialViewState={{
          longitude: 37.628,
          latitude: 55.757,
          zoom: 11,
        }}
        mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
        interactive={true}
      >
        {/* Линии маршрута */}
        <Source id="route-source" type="geojson" data={routeFeatures}>
          <Layer
            id="route-layer"
            type="line"
            paint={{
              "line-color": "#e30b13", // Цвет МосТранс
              "line-width": 4,
              "line-opacity": 0.7,
            }}
          />
        </Source>

        {/* Остановки */}
        <Source id="stops-source" type="geojson" data={stopFeatures}>
          <Layer
            id="stops-layer"
            type="circle"
            paint={{
              "circle-radius": 5,
              "circle-color": "#ffffff",
              "circle-stroke-width": 2,
              "circle-stroke-color": "#e30b13",
            }}
          />
        </Source>

        {/* Прогноз (дополнительные слои) */}
        {forecast?.features && (
          <Source id="forecast-source" type="geojson" data={forecast}>
            <Layer
              id="forecast-layer"
              type="circle"
              paint={{
                "circle-radius": 8,
                "circle-color": "#128a85",
                "circle-stroke-width": 2,
                "circle-stroke-color": "#ffffff",
              }}
            />
          </Source>
        )}
      </MapLibreMap>

      <div className="map-key" style={{ position: "absolute", bottom: "10px", left: "10px", background: "white", padding: "5px", borderRadius: "5px" }}>
        <i style={{ display: "inline-block", width: "10px", height: "10px", backgroundColor: "#e30b13", marginRight: "5px" }} /> Маршрут 
        <i style={{ display: "inline-block", width: "8px", height: "8px", borderRadius: "50%", border: "2px solid #e30b13", marginLeft: "10px", marginRight: "5px" }} /> Остановка 
        <i style={{ display: "inline-block", width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#cc7a32", marginLeft: "10px", marginRight: "5px" }} /> Объект города
      </div>
    </div>
  );
}
