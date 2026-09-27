const https = require('https');
const fs = require('fs');
const path = require('path');

// We use Overpass API to get the exact real geometry of all 10 hackathon tram routes in Moscow
const query = `
[out:json];
area["name"="Москва"]->.searchArea;
(
  relation["route"="tram"]["ref"~"^1$|^5$|^7$|^11$|^12$|^17$|^25$|^26$|^28$|^50$"](area.searchArea);
);
out geom;
`;

const url = 'https://overpass-api.de/api/interpreter?data=' + encodeURIComponent(query);

console.log("Загрузка геометрии 10 маршрутов из OpenStreetMap (Overpass API)...");

https.get(url, { headers: { 'User-Agent': 'TramRidershipApp/1.0' } }, (res) => {
  let body = '';
  res.on('data', chunk => {
    body += chunk;
  });
  res.on('end', () => {
    try {
      const data = JSON.parse(body);
      let routeGeometries = {};
      
      data.elements.forEach(el => {
        if (el.type === 'relation' && el.members && el.tags && el.tags.ref) {
          let ref = el.tags.ref;
          if (!routeGeometries[ref]) routeGeometries[ref] = [];
          
          el.members.forEach(mem => {
            if (mem.type === 'way' && mem.geometry) {
              let wayCoords = [];
              mem.geometry.forEach(g => {
                wayCoords.push([g.lon, g.lat]);
              });
              if (wayCoords.length > 0) {
                routeGeometries[ref].push(wayCoords);
              }
            }
          });
        }
      });
      
      console.log('Найдено маршрутов:', Object.keys(routeGeometries).length);
      
      const outFile = path.join(__dirname, '../frontend/public/moscow_tram_routes.json');
      fs.writeFileSync(outFile, JSON.stringify(routeGeometries, null, 2));
      console.log('Сохранено в', outFile);
      
    } catch(e) {
      console.error('Ошибка:', e.message);
    }
  });
}).on('error', (e) => {
  console.error("Network error:", e.message);
});
