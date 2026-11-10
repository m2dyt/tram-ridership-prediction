export function evaluationScoreRows(scores, route) {
  const methods = {
    model: "Проверяемая модель",
    seasonal_naive: "Сезонная база",
    regression: "Регрессия",
  };
  const slices = { all: "Все интервалы", peak: "Часы пик" };
  return scores.map((score) => ({
    ...score,
    methodLabel: methods[score.method] || score.method,
    routeLabel:
      score.route_id == null
        ? "Все маршруты"
        : score.route_id === route?.route?.id
          ? `Маршрут ${route.route.number}`
          : score.route_id,
    sliceLabel: slices[score.demand_slice] || score.demand_slice,
  }));
}

export function peakRuleLabel(rule) {
  if (
    rule ===
    "Hourly Moscow intervals starting at 07–09 or 17–19; daily/monthly peak slice is empty"
  )
    return "Часовые интервалы с началом в 07–09 или 17–19 по Москве. Для дневного и месячного шага часы пик не выделяются.";
  return rule;
}
