const https = require('https');
const fs = require('fs');
const path = require('path');

// We use Overpass API to get the exact real geometry of Tram 17 in Moscow
const query = `
[out:json];
relation["route"="tram"]["ref"="17"](55.8,37.6,55.9,37.7);
out geom;
`;

const url = 'https://overpass-api.de/api/interpreter?data=' + encodeURIComponent(query);

console.log("Загрузка геометрии маршрута 17 из OpenStreetMap (Overpass API)...");

https.get(url, { headers: { 'User-Agent': 'TramRidershipApp/1.0' } }, (res) => {
  let body = '';
  res.on('data', chunk => {
    body += chunk;
  });
  res.on('end', () => {
    try {
      const data = JSON.parse(body);
      let coordinates = [];
      let features = [];
      
      data.elements.forEach(el => {
        if (el.type === 'relation' && el.members) {
          el.members.forEach(mem => {
            if (mem.type === 'way' && mem.geometry) {
              mem.geometry.forEach(g => {
                coordinates.push([g.lon, g.lat]);
              });
            }
          });
        }
      });
      
      console.log('Извлечено точек пути:', coordinates.length);
      
      const outFile = path.join(__dirname, '../frontend/public/tram17_route.json');
      fs.writeFileSync(outFile, JSON.stringify({ coordinates }));
      console.log('Сохранено в', outFile);
      
    } catch(e) {
      console.error('Ошибка:', e.message);
    }
  });
}).on('error', (e) => {
  console.error("Network error:", e.message);
});
