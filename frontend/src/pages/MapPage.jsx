import React, { useRef, useState, useEffect, useMemo, useCallback } from "react";
import { Map, Source, Layer, Popup, NavigationControl } from "@vis.gl/react-maplibre";
import { ClusterComponent } from "../components/ClusterComponent";
import { useObservations } from "../api/hooks";
import {
  CARTO_MAP_STYLE,
  FALLBACK_MAP_STYLE,
  shouldFallbackToLocalMapStyle,
} from "../domain/mapStyle.js";

function getBoundsForRoute(features, stops) {
  let minLng = 180, maxLng = -180, minLat = 90, maxLat = -90;
  let count = 0;

  const addPoint = (lng, lat) => {
    const numLng = Number(lng);
    const numLat = Number(lat);
    if (!isNaN(numLng) && !isNaN(numLat) && numLng > 35 && numLng < 40 && numLat > 54 && numLat < 57) {
      if (numLng < minLng) minLng = numLng;
      if (numLng > maxLng) maxLng = numLng;
      if (numLat < minLat) minLat = numLat;
      if (numLat > maxLat) maxLat = numLat;
      count++;
    }
  };

  const visitCoordinates = (value) => {
    if (!Array.isArray(value)) return;
    if (value.length >= 2 && value.slice(0, 2).every(Number.isFinite)) {
      addPoint(value[0], value[1]);
      return;
    }
    value.forEach(visitCoordinates);
  };

  if (Array.isArray(features)) features.forEach(f => visitCoordinates(f.geometry?.coordinates));

  if (Array.isArray(stops)) {
    stops.forEach(s => {
      const lng = s.longitude ?? s.geometry?.coordinates?.[0];
      const lat = s.latitude ?? s.geometry?.coordinates?.[1];
      if (lng != null && lat != null) {
        addPoint(lng, lat);
      }
    });
  }

  if (count > 0) {
    if (minLng === maxLng) { minLng -= 0.01; maxLng += 0.01; }
    if (minLat === maxLat) { minLat -= 0.01; maxLat += 0.01; }
    return [[minLng, minLat], [maxLng, maxLat]];
  }
  return null;
}

export default function MapPage({ route, caps }) {
  const mapRef = useRef(null);
  const [isMapReady, setIsMapReady] = useState(false);
  const [popUpData, setPopUpData] = useState(null);
  const [mapStyle, setMapStyle] = useState(CARTO_MAP_STYLE);
  const [usesFallbackStyle, setUsesFallbackStyle] = useState(false);

  const realGeom = useMemo(() => (route?.directions || []).flatMap(direction => {
    const geometry = direction.geometry;
    if (geometry?.type === "LineString") {
      return [{ type: "Feature", geometry }];
    }
    if (geometry?.type === "MultiLineString") {
      return geometry.coordinates.map(coordinates => ({
        type: "Feature",
        geometry: { type: "LineString", coordinates },
      }));
    }
    return [];
  }), [route?.directions]);

  const stopsData = useMemo(() => {
    const sList = route?.stops;
    if (!sList) return [];
    return sList.map(s => {
      const coords = s.geometry?.coordinates || [s.longitude, s.latitude];
      const [lng, lat] = coords;
      return { id: s.id, name: s.name, longitude: lng, latitude: lat };
    });
  }, [route?.stops]);

  const directionName = useMemo(() => {
    if (!stopsData || stopsData.length < 2) return route?.route?.name || '—';
    return `${stopsData[0].name} — ${stopsData[stopsData.length - 1].name}`;
  }, [stopsData, route]);

  const routeLengthKm = useMemo(() => {
    if (!realGeom.length) return null;
    let total = 0;
    realGeom.forEach(f => {
      const coords = f.geometry.coordinates;
      for (let i = 1; i < coords.length; i++) {
        const dlat = (coords[i][1] - coords[i-1][1]) * 111100;
        const dlon = (coords[i][0] - coords[i-1][0]) * 62500;
        total += Math.sqrt(dlat*dlat + dlon*dlon);
      }
    });
    return (total / 1000).toFixed(2);
  }, [realGeom]);

  const profile = caps?.observation_profiles?.find(item =>
    item.route_ids?.includes(route?.route?.id),
  );
  const observationWindow = useMemo(() => {
    if (!profile?.history_end) return null;
    const end = new Date(profile.history_end);
    const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
    return { from: start.toISOString(), to: end.toISOString() };
  }, [profile?.history_end]);
  const observationsQuery = useObservations(profile && observationWindow ? {
    dataset_revision_id: caps.dataset_revision_id,
    observation_profile_id: profile.id,
    route_id: route?.route?.id,
    ...observationWindow,
  } : null);
  const observedPoints = observationsQuery.data || [];
  const knownPoints = observedPoints.filter(point => point.value != null);
  const observedTotal = knownPoints.reduce((total, point) => total + point.value, 0);

  const bounds = useMemo(() => {
    return getBoundsForRoute(realGeom, stopsData);
  }, [realGeom, stopsData, route]);

  const fitToBounds = useCallback((customBounds = bounds) => {
    if (!customBounds || !mapRef.current) return;
    const map = mapRef.current.getMap ? mapRef.current.getMap() : mapRef.current;
    if (!map) return;
    try {
      if (typeof map.resize === "function") {
        map.resize();
      }
      map.fitBounds(customBounds, {
        padding: { top: 70, bottom: 70, left: 70, right: 70 },
        duration: 1000,
        maxZoom: 14.5
      });
    } catch (err) {
      console.warn("fitBounds failed:", err);
    }
  }, [bounds]);

  // Automatically fit map view whenever route data or map readiness updates
  useEffect(() => {
    if (isMapReady && bounds) {
      fitToBounds(bounds);
    }
  }, [bounds, isMapReady, fitToBounds]);

  const handleMapLoad = (e) => {
    setIsMapReady(true);
    if (bounds) {
      try {
        const map = e.target;
        map.fitBounds(bounds, {
          padding: { top: 70, bottom: 70, left: 70, right: 70 },
          duration: 1000,
          maxZoom: 14.5
        });
      } catch (err) {
        console.warn("handleMapLoad fitBounds failed:", err);
      }
    }
  };

  const handleMapError = (event) => {
    if (usesFallbackStyle || !shouldFallbackToLocalMapStyle(event)) return;
    setMapStyle(FALLBACK_MAP_STYLE);
    setUsesFallbackStyle(true);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px", paddingBottom: "6rem" }}>
      <div className="stat-grid">
        <div className="stat stat-pattern">
          <div className="stat-top">
            <span className="stat-label">Текущий маршрут</span>
            <img src="/icons/tram_icon.svg" alt="" className="stat-icon" />
          </div>
          <strong className="stat-value">№ {route?.route?.number || '—'}</strong>
          <span className="stat-sub">Трамвайная сеть Москвы</span>
        </div>

        <div className="stat stat-pattern" style={{ gridColumn: 'span 2' }}>
          <div className="stat-top">
            <span className="stat-label">Направление движения</span>
            <img src="/icons/geo_icon.svg" alt="" className="stat-icon" />
          </div>
          <strong className="stat-value word-stat">{directionName}</strong>
          <span className="stat-sub">Конечные остановочные пункты</span>
        </div>

        <div className="stat stat-pattern">
          <div className="stat-top">
            <span className="stat-label">Остановок на маршруте</span>
            <img src="/icons/geo_icon.svg" alt="" className="stat-icon" />
          </div>
          <strong className="stat-value">{stopsData.length || '—'}</strong>
          <span className="stat-sub">Посадочные платформы</span>
        </div>

        <div className="stat stat-pattern">
          <div className="stat-top">
            <span className="stat-label">Протяжённость (км)</span>
            <img src="/icons/Column_graphs.svg" alt="" className="stat-icon" />
          </div>
          <strong className="stat-value">{routeLengthKm || '—'}</strong>
          <span className="stat-sub">Длина рельсового полотна</span>
        </div>

        <div className="stat stat-pattern">
          <div className="stat-top">
            <span className="stat-label">Факт за последние 24 часа</span>
            <img src="/icons/signal_icon.svg" alt="" className="stat-icon" />
          </div>
          <strong className="stat-value">
            {knownPoints.length ? observedTotal.toLocaleString("ru-RU") : "Нет данных"}
          </strong>
          <span className="stat-sub">
            {knownPoints.length ? `Заполнено часов: ${knownPoints.length} из 24` : "В базе нет наблюдений за этот период"}
          </span>
        </div>
      </div>
      
      <div className="map-shell" style={{ position: "relative", height: "700px", borderRadius: "16px", overflow: 'hidden', border: '1px solid var(--border-color)', boxShadow: '0 4px 20px rgba(0,0,0,0.05)' }}>
        {usesFallbackStyle && (
          <div
            role="status"
            style={{
              position: "absolute",
              top: "14px",
              left: "50%",
              transform: "translateX(-50%)",
              zIndex: 10,
              padding: "8px 12px",
              borderRadius: "8px",
              background: "#ffffff",
              color: "#334155",
              boxShadow: "0 2px 10px rgba(0,0,0,0.1)",
              fontSize: "13px",
            }}
          >
            Подложка недоступна: маршрут показан без неё
          </div>
        )}
        {/* Floating Button to re-center to route */}
        <button
          onClick={() => fitToBounds()}
          title="Приблизить к маршруту"
          style={{
            position: "absolute",
            top: "14px",
            left: "14px",
            zIndex: 10,
            background: "#ffffff",
            color: "#1e293b",
            border: "1px solid rgba(0,0,0,0.12)",
            borderRadius: "8px",
            padding: "8px 14px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "13px",
            fontWeight: "600",
            cursor: "pointer",
            boxShadow: "0 2px 10px rgba(0,0,0,0.1)",
            transition: "all 0.2s ease"
          }}
          onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-1px)"; e.currentTarget.style.boxShadow = "0 4px 14px rgba(0,0,0,0.15)"; }}
          onMouseLeave={e => { e.currentTarget.style.transform = "none"; e.currentTarget.style.boxShadow = "0 2px 10px rgba(0,0,0,0.1)"; }}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#0076bc" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="22" y1="12" x2="18" y2="12" />
            <line x1="6" y1="12" x2="2" y2="12" />
            <line x1="12" y1="6" x2="12" y2="2" />
            <line x1="12" y1="22" x2="12" y2="18" />
          </svg>
          К маршруту
        </button>

        <Map
            style={{ width: "100%", height: "100%" }}
            ref={mapRef}
            onLoad={handleMapLoad}
            onError={handleMapError}
            mapStyle={mapStyle}
            initialViewState={{ longitude: 37.6173, latitude: 55.7558, zoom: 11 }}
            maxZoom={20}
            minZoom={0}
        >
          <NavigationControl position="top-right" />

          {realGeom.map((feature, idx) => (
             <Source key={idx} id={`route-${idx}`} type="geojson" data={feature}>
               <Layer 
                  id={`route-line-${idx}`} 
                  type="line" 
                  paint={{ "line-color": "#0076bc", "line-width": 5, "line-opacity": 0.9 }} 
               />
             </Source>
          ))}
          
          <ClusterComponent data={stopsData} setPopUpData={setPopUpData} />
          
          {popUpData && popUpData.popUpData && (
             <Popup
               longitude={popUpData.longitude || popUpData.popUpData.longitude}
               latitude={popUpData.latitude || popUpData.popUpData.latitude}
               anchor="bottom"
               offset={10}
               onClose={() => setPopUpData(null)}
               closeOnClick={false}
             >
               <div style={{ padding: '8px', color: '#333', minWidth: '150px' }}>
                 <h4 style={{ margin: '0 0 5px 0', fontSize: '14px', borderBottom: '1px solid #eee', paddingBottom: '5px' }}>Остановка</h4>
                 <p style={{ margin: 0, fontSize: '13px', fontWeight: '500' }}>{popUpData.popUpData.name}</p>
                 <div style={{ marginTop: '10px', fontSize: '11px', color: '#666' }}>
                   Координаты: {Number(popUpData.popUpData.longitude).toFixed(4)}, {Number(popUpData.popUpData.latitude).toFixed(4)}
                 </div>
               </div>
             </Popup>
          )}
        </Map>
      </div>
    </div>
  );
}
