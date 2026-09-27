import React, { useMemo, useState } from "react";
import MapLibreMap, { Source, Layer } from "@vis.gl/react-maplibre";
import { mapLib } from "./mapLib.js";
import {
  CARTO_MAP_STYLE,
  FALLBACK_MAP_STYLE,
  shouldFallbackToLocalMapStyle,
} from "../domain/mapStyle.js";

const EMPTY_CONTEXT = [];

export default function Map({ route, forecast, context = EMPTY_CONTEXT }) {
  const [mapStyle, setMapStyle] = useState(CARTO_MAP_STYLE);
  const [usesFallbackStyle, setUsesFallbackStyle] = useState(false);

  const handleMapError = (event) => {
    if (usesFallbackStyle || !shouldFallbackToLocalMapStyle(event)) return;
    setMapStyle(FALLBACK_MAP_STYLE);
    setUsesFallbackStyle(true);
  };

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
        mapLib={mapLib}
        initialViewState={{
          longitude: 37.628,
          latitude: 55.757,
          zoom: 11,
        }}
        mapStyle={mapStyle}
        onError={handleMapError}
        interactive={true}
      >
        {/* Линии маршрута */}
        <Source id="route-source" type="geojson" data={routeFeatures}>
          <Layer
            id="route-layer"
            type="line"
            paint={{
              "line-color": "#0076bc", // Цвет МосТранс
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
              "circle-stroke-color": "#0076bc",
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

      {usesFallbackStyle && (
        <div
          role="status"
          style={{
            position: "absolute",
            top: "10px",
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 2,
            padding: "6px 10px",
            borderRadius: "8px",
            background: "#ffffff",
            color: "#334155",
            boxShadow: "0 2px 10px rgba(0,0,0,0.1)",
            fontSize: "12px",
          }}
        >
          Подложка недоступна: маршрут показан без неё
        </div>
      )}

      <div className="map-key" style={{ position: "absolute", bottom: "10px", left: "10px", background: "white", padding: "5px", borderRadius: "5px" }}>
        <i style={{ display: "inline-block", width: "10px", height: "10px", backgroundColor: "#0076bc", marginRight: "5px" }} /> Маршрут 
        <i style={{ display: "inline-block", width: "8px", height: "8px", borderRadius: "50%", border: "2px solid #0076bc", marginLeft: "10px", marginRight: "5px" }} /> Остановка 
        <i style={{ display: "inline-block", width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#cc7a32", marginLeft: "10px", marginRight: "5px" }} /> Объект города
      </div>
    </div>
  );
}
