const fs = require('fs');

const routeGeom = JSON.parse(fs.readFileSync('frontend/public/moscow_tram_routes.json', 'utf8'));
const lines = fs.readFileSync('data/trams/stop_from_repo.csv', 'utf8').split('\n').slice(1);
const stops = {};

function distMeters(lon1, lat1, lon2, lat2) {
  const dlat = (lat2 - lat1) * 111100;
  const dlon = (lon2 - lon1) * 62500;
  return Math.sqrt(dlat*dlat + dlon*dlon);
}

for (const line of lines) {
  if (!line) continue;
  const parts = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (c === '"') {
      inQuotes = !inQuotes;
    } else if (c === ',' && !inQuotes) {
      parts.push(current);
      current = '';
    } else {
      current += c;
    }
  }
  parts.push(current);
  
  if (parts.length < 9) continue;
  const type = parts[4];
  if (type !== 'tram') continue;
  const num = parts[5];
  const name = parts[2];
  const lon = parseFloat(parts[parts.length - 2]);
  const lat = parseFloat(parts[parts.length - 1]);
  if (!stops[num]) stops[num] = [];
  stops[num].push({ id: parts[1], name, geometry: { coordinates: [lon, lat] } });
}

let removedCount = 0;
// Remove duplicates and filter by distance to route geometry
for (const num in stops) {
  const uniqueStops = [];
  const seenIds = new Set();
  
  const geomLines = routeGeom[num];
  
  for (const s of stops[num]) {
    if (seenIds.has(s.id)) continue;
    seenIds.add(s.id);
    
    // If we have OSM geometry, filter out stops > 200m away
    if (geomLines) {
      let minDist = Infinity;
      for (const line of geomLines) {
        for (const coord of line) {
          const d = distMeters(s.geometry.coordinates[0], s.geometry.coordinates[1], coord[0], coord[1]);
          if (d < minDist) minDist = d;
        }
      }
      if (minDist > 200) {
        removedCount++;
        continue;
      }
    }
    
    uniqueStops.push(s);
  }
  stops[num] = uniqueStops;
}

fs.writeFileSync('frontend/public/moscow_tram_stops.json', JSON.stringify(stops));
console.log('Stops saved:', Object.keys(stops).length, 'routes. Removed outlier stops:', removedCount);
