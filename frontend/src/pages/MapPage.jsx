import React, { useRef, useState } from "react";
import { Map, Source, Layer } from "@vis.gl/react-maplibre";
import { ClusterComponent } from "../components/ClusterComponent";

export default function MapPage({ route }) {
  const mapRef = useRef(null);
  const [popUpData, setPopUpData] = useState(null);

  // Transform route points/stops to data that supercluster expects
  const stopsData = React.useMemo(() => {
    if (!route?.stops) return [];
    return route.stops.map(s => {
       const [lng, lat] = s.geometry.coordinates;
       return { id: s.id, name: s.name, longitude: lng, latitude: lat };
    });
  }, [route]);

  return (
    <div style={{ height: "600px", minHeight: "600px", position: "relative", marginBottom: "2rem" }}>
      <div className="stat-grid" style={{ marginBottom: "20px" }}>
        <div className="stat">
          <span>Текущий маршрут</span>
          <strong>{route?.route?.number || '—'}</strong>
        </div>
        <div className="stat">
          <span>Направление</span>
          <strong>{route?.route?.name || '—'}</strong>
        </div>
        <div className="stat">
           <span>Остановок на маршруте</span>
           <strong>{stopsData.length}</strong>
        </div>
      </div>
      
      <div className="map-shell" style={{ height: "100%", borderRadius: "16px", overflow: 'hidden' }}>
        <Map
            style={{ width: "100%", height: "100%" }}
            ref={mapRef}
            mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
            initialViewState={{ longitude: 37.6173, latitude: 55.7558, zoom: 11 }}
            maxZoom={20}
            minZoom={0}
        >
          {/* Display route directions via GeoJSON */}
          {route?.directions?.map((d, idx) => (
             <Source key={idx} id={`route-${idx}`} type="geojson" data={d.geometry}>
               <Layer 
                  id={`route-line-${idx}`} 
                  type="line" 
                  paint={{ "line-color": "#e30b13", "line-width": 4, "line-opacity": 0.8 }} 
               />
             </Source>
          ))}
          <ClusterComponent data={stopsData} setPopUpData={setPopUpData} />
          {popUpData && (
             <div style={{
                 position: 'absolute', 
                 left: 20, 
                 bottom: 20, 
                 background: 'white', 
                 padding: 15, 
                 borderRadius: 8,
                 boxShadow: '0 2px 10px rgba(0,0,0,0.2)'
             }}>
                 <h3>Остановка</h3>
                 <p>{popUpData.popUpData?.name}</p>
                 <button onClick={() => setPopUpData(null)}>Закрыть</button>
             </div>
          )}
        </Map>
      </div>
    </div>
  );
}
