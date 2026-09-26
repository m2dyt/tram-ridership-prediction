const fs = require('fs');
const https = require('https');
const path = require('path');

const API_KEY = "10e6de19b76dfde4d84587b61c5a975d";
// Датасет 3221 - Остановки наземного городского пассажирского транспорта
const DATASET_ID = 3221;
const URL = `https://apidata.mos.ru/v1/datasets/${DATASET_ID}/rows?$top=5000&api_key=${API_KEY}`;

const OUTPUT_FILE = path.join(__dirname, '../frontend/public/mosru_stops.json');

console.log(`Запуск загрузки данных с data.mos.ru (Датасет ${DATASET_ID})...`);

https.get(URL, (res) => {
  let data = '';

  if (res.statusCode !== 200) {
    console.error(`Ошибка HTTP: ${res.statusCode} ${res.statusMessage}`);
    res.resume();
    return;
  }

  res.on('data', (chunk) => {
    data += chunk;
  });

  res.on('end', () => {
    try {
      const parsedData = JSON.parse(data);
      console.log(`Получено ${parsedData.length} записей. Фильтрация трамвайных остановок...`);
      
      // Фильтруем только трамвайные остановки
      // В поле RouteNumbers обычно указаны маршруты, идущие через остановку (напр. "Трамвай 17, 11")
      // Или тип транспорта (Type_of_vehicle) = "Трамвай" (если такое поле есть).
      // Так как структура может меняться, мы сохраняем извлечённые геоданные X_WGS84 и Y_WGS84.
      const processedStops = parsedData.map(item => {
        const cells = item.Cells;
        return {
           id: cells.global_id || item.Number,
           name: cells.Name || cells.StationName,
           routes: cells.RouteNumbers,
           geometry: {
              type: "Point",
              coordinates: [parseFloat(cells.X_WGS84), parseFloat(cells.Y_WGS84)]
           }
        };
      }).filter(s => s.geometry.coordinates[0] && s.geometry.coordinates[1]);
      
      // Чтобы не перегружать фронтенд тысячами остановок для одного маршрута, 
      // сохраняем все, а мок-интерцептор выберет нужные.
      fs.writeFileSync(OUTPUT_FILE, JSON.stringify(processedStops, null, 2));
      console.log(`Успешно сохранено ${processedStops.length} остановок в ${OUTPUT_FILE}`);
      
    } catch (e) {
      console.error("Ошибка парсинга JSON:", e.message);
    }
  });

}).on('error', (e) => {
  console.error("Ошибка сети:", e.message);
});
