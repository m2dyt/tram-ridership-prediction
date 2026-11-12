import test from "node:test";
import assert from "node:assert/strict";
import { forecastIssue, forecastModelLabel } from "../src/domain/forecast.js";

const profile = {
  availability: "available",
  allowed_as_of_start: "2026-11-01T00:00:00+03:00",
  allowed_as_of_end: "2026-11-10T00:00:00+03:00",
  forecast_start_min: "2026-11-11T00:00:00+03:00",
  forecast_start_max: "2026-11-15T00:00:00+03:00",
  start_alignment: "local_midnight",
};
const fields = {
  profile,
  role: "operator",
  asOf: "2026-11-10T00:00",
  start: "2026-11-11T00:00",
  now: new Date("2026-11-10T12:00:00+03:00"),
};

test("forecast creation respects role, availability, date range and alignment", () => {
  assert.equal(forecastIssue(fields), null);
  assert.match(forecastIssue({ ...fields, role: "viewer" }), /оператор/iu);
  assert.match(
    forecastIssue({
      ...fields,
      profile: {
        ...profile,
        availability: "unavailable",
        unavailable_reason: "Недостаточно истории",
      },
    }),
    /Недостаточно истории/,
  );
  assert.match(
    forecastIssue({ ...fields, start: "2026-11-16T00:00" }),
    /диапазон/iu,
  );
  assert.match(
    forecastIssue({ ...fields, start: "2026-11-11T12:00" }),
    /полноч/iu,
  );
});

test("forecast method comes from the calculation rather than health", () => {
  assert.equal(
    forecastModelLabel({ method: "tram_bundle", version: "v1" }),
    "Обученная модель · v1",
  );
  assert.equal(
    forecastModelLabel({
      method: "tram_bundle",
      version: "v1",
      is_baseline: true,
    }),
    "Базовая модель по сезонному профилю · v1",
  );
  assert.equal(
    forecastModelLabel({
      method: "tram_bundle",
      version: "v1",
      is_baseline: false,
    }),
    "Обученная модель · v1",
  );
  assert.match(
    forecastModelLabel({ method: "seasonal_naive_v1", version: "1" }),
    /Сезонная/,
  );
  assert.equal(forecastModelLabel(null), "Метод не указан");
  assert.equal(
    forecastModelLabel({ method: "other", version: "1" }),
    "other · 1",
  );
});

test("forecast rejects future data and annual starts outside month boundaries", () => {
  assert.match(
    forecastIssue({ ...fields, now: new Date("2026-11-09T00:00:00+03:00") }),
    /будущем/,
  );
  assert.match(
    forecastIssue({
      ...fields,
      profile: { ...profile, start_alignment: "month_start" },
    }),
    /первого числа/,
  );
});

import { exportCsv } from "../src/domain/format.js";

test("aggregate CSV exports its named group and coverage fields", () => {
  const csv = exportCsv(
    [{ group: "Остановка 1", value: 12, coverage: 0.9 }],
    ["group", "value", "coverage"],
  );
  assert.match(csv, /group,value,coverage/);
  assert.match(csv, /"Остановка 1","12","0.9"/);
});

import {
  explainForecastText,
  forecastDateRange,
} from "../src/domain/forecast.js";

test("known limitations are translated while unknown text remains intact", () => {
  assert.match(
    explainForecastText(
      "Synthetic demonstration data; not real ridership or measured model accuracy",
    ),
    /синтетическ/iu,
  );
  assert.match(
    explainForecastText(
      "Stop values are an estimated split of the route total",
    ),
    /оценочн/iu,
  );
  assert.match(
    explainForecastText("Seasonal baseline; no model training was performed"),
    /обуча/iu,
  );
  assert.match(
    explainForecastText(
      "Model bundle test-v1 is a seasonal-profile baseline; no model was fitted",
    ),
    /test-v1/,
  );
  assert.equal(explainForecastText("Unknown warning"), "Unknown warning");
  assert.equal(explainForecastText("constructor"), "constructor");
});

test("one available date is shown once rather than as a repeated range", () => {
  assert.equal(
    forecastDateRange("2026-11-10T00:00:00+03:00", "2026-11-09T21:00:00Z"),
    "10 нояб. 2026 г., 00:00",
  );
  assert.match(
    forecastDateRange("2026-11-10T00:00:00+03:00", "2026-11-11T00:00:00+03:00"),
    / — /,
  );
});

import { forecastCoverageLabel } from "../src/domain/forecast.js";

test("coverage displays loading and error states without a misleading zero", () => {
  assert.equal(
    forecastCoverageLabel({ loading: true, points: [] }),
    "Загрузка…",
  );
  assert.equal(
    forecastCoverageLabel({ error: new Error("network"), points: [] }),
    "Нет данных",
  );
  assert.equal(forecastCoverageLabel({ points: [] }), "Нет данных");
  assert.equal(
    forecastCoverageLabel({ points: [{ value: 0 }, { value: null }] }),
    "1 / 2",
  );
});

test("reports of a trained model are explained in Russian", () => {
  assert.equal(
    explainForecastText(
      "Trained model svc-check checked on folds after its training history; the seasonal baseline is shown on the same intervals",
    ),
    "Проверена обученная модель svc-check на днях после конца её обучающей истории; сезонная база показана на тех же часах.",
  );
  assert.match(
    explainForecastText("Both methods are scored on the same intervals only"),
    /одних и тех же часах/u,
  );
});
