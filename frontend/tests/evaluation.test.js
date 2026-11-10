import test from "node:test";
import assert from "node:assert/strict";
import {
  evaluationModelLabel,
  evaluationStatusLabel,
} from "../src/domain/evaluation.js";

test("название оцениваемой модели соответствует отчёту", () => {
  assert.equal(
    evaluationModelLabel({ is_baseline: true, method: "seasonal_naive_v1" }),
    "Сезонная базовая модель",
  );
  assert.equal(
    evaluationModelLabel({
      is_baseline: false,
      method: "tram_bundle",
      version: "v2",
    }),
    "Обученная модель · v2",
  );
  assert.equal(
    evaluationModelLabel({
      is_baseline: true,
      method: "tram_bundle",
      version: "v2",
    }),
    "Базовая модель по сезонному профилю · v2",
  );
  assert.equal(
    evaluationModelLabel({ is_baseline: true, method: "other" }),
    "Базовая модель · other",
  );
  assert.equal(
    evaluationModelLabel({ is_baseline: false, method: "other" }),
    "Модель · other",
  );
  assert.equal(evaluationModelLabel(null), "Модель не указана");
});

test("статус оценки не обещает точность при недостатке данных", () => {
  assert.equal(evaluationStatusLabel("complete"), "Проверка завершена");
  assert.equal(
    evaluationStatusLabel("insufficient_history"),
    "Недостаточно истории для проверки",
  );
  assert.equal(evaluationStatusLabel("unavailable"), "Проверка недоступна");
});
