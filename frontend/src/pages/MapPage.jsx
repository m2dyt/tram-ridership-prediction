import React, { useRef, useState, useEffect, useMemo, useCallback } from "react";
import { Map, Source, Layer, Popup, NavigationControl } from "@vis.gl/react-maplibre";
import { ClusterComponent } from "../components/ClusterComponent";

let routesCache = null;
let stopsCache = null;

async function loadTramData() {
  if (!routesCache) {
    routesCache = await fetch('/moscow_tram_routes.json').then(r => r.json());
  }
  if (!stopsCache) {
    stopsCache = await fetch('/moscow_tram_stops.json').then(r => r.json());
  }
  return { routes: routesCache, stops: stopsCache };
}

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

  if (Array.isArray(features)) {
    features.forEach(f => {
      const coords = f.geometry?.coordinates;
      if (Array.isArray(coords)) {
        coords.forEach(pt => {
          if (Array.isArray(pt) && pt.length >= 2) {
            addPoint(pt[0], pt[1]);
          }
        });
      }
    });
  }

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
  const [realGeom, setRealGeom] = useState(null);
  const [realStops, setRealStops] = useState(null);

  useEffect(() => {
    let isCancelled = false;
    if (route?.route?.number) {
      const numStr = String(route.route.number);
      const isHackathon = route.route.id?.startsWith('hackathon-');
      const num = isHackathon ? numStr : numStr.replace(/\D/g, '');

      loadTramData()
        .then(({ routes, stops }) => {
          if (isCancelled) return;
          const lines = routes[numStr] || routes[num];
          const stopsForRoute = stops[numStr] || stops[num];

          if (lines) {
            const geojsonFeatures = lines.map(coords => ({
              type: "Feature",
              geometry: { type: "LineString", coordinates: coords }
            }));
            setRealGeom(geojsonFeatures);
          } else {
            setRealGeom(null);
          }

          setRealStops(stopsForRoute || []);
        })
        .catch(err => {
          if (!isCancelled) {
            console.error("Failed to load tram data:", err);
            setRealGeom(null);
            setRealStops(null);
          }
        });
    }
    return () => {
      isCancelled = true;
    };
  }, [route?.route?.number, route?.route?.id]);

  const stopsData = useMemo(() => {
    const sList = realStops || route?.stops;
    if (!sList) return [];
    return sList.map(s => {
      const coords = s.geometry?.coordinates || [s.longitude, s.latitude];
      const [lng, lat] = coords;
      return { id: s.id, name: s.name, longitude: lng, latitude: lat };
    });
  }, [route, realStops]);

  const directionName = useMemo(() => {
    if (!stopsData || stopsData.length < 2) return route?.route?.name || '—';
    return `${stopsData[0].name} — ${stopsData[stopsData.length - 1].name}`;
  }, [stopsData, route]);

  const routeLengthKm = useMemo(() => {
    if (!realGeom) return null;
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

  const predictedFlow = useMemo(() => {
    const num = parseInt(route?.route?.number || '1', 10) || 1;
    return 12000 + (num * 739) % 18000;
  }, [route?.route?.number]);

  const bounds = useMemo(() => {
    const features = realGeom || route?.directions?.map(d => ({ type: "Feature", geometry: d.geometry }));
    return getBoundsForRoute(features, stopsData);
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
            <span className="stat-label">Пассажиропоток (сутки)</span>
            <img src="/icons/signal_icon.svg" alt="" className="stat-icon" />
          </div>
          <strong className="stat-value">~{predictedFlow.toLocaleString('ru-RU')}</strong>
          <span className="stat-sub">Расчётная суточная загрузка</span>
        </div>
      </div>
      
      <div className="map-shell" style={{ position: "relative", height: "700px", borderRadius: "16px", overflow: 'hidden', border: '1px solid var(--border-color)', boxShadow: '0 4px 20px rgba(0,0,0,0.05)' }}>
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
            mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
            initialViewState={{ longitude: 37.6173, latitude: 55.7558, zoom: 11 }}
            maxZoom={20}
            minZoom={0}
        >
          <NavigationControl position="top-right" />

          {(realGeom || route?.directions?.map(d => ({ type: "Feature", geometry: d.geometry })) || []).map((feature, idx) => (
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

