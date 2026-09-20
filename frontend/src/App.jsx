import React, { useMemo, useState } from "react";
import { createClient } from "./api/client.js";
import {
  Badge,
  Empty,
  ErrorBox,
  Freshness,
  Loading,
  useResource,
} from "./components/Common.jsx";
import Forecast from "./features/Forecast.jsx";
import History from "./features/History.jsx";
import Evaluations from "./features/Evaluations.jsx";
import Occupancy from "./features/Occupancy.jsx";
import Context from "./features/Context.jsx";

const tabs = [
  ["forecast", "01", "Прогноз"],
  ["history", "02", "История"],
  ["evaluations", "03", "Качество"],
  ["occupancy", "04", "Наполненность"],
  ["context", "05", "Городской контекст"],
];
function Logo() {
  return (
    <span className="logo-icon">
      <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <path
          d="M10 3h12M16 3v4M9 25l-3 5m17-5 3 5M8 14h16"
          stroke="currentColor"
          strokeWidth="2"
        />
        <rect
          x="7"
          y="7"
          width="18"
          height="19"
          rx="5"
          stroke="currentColor"
          strokeWidth="2"
        />
        <circle cx="11" cy="21" r="1.5" fill="currentColor" />
        <circle cx="21" cy="21" r="1.5" fill="currentColor" />
      </svg>
    </span>
  );
}

export default function App() {
  const [token, setToken] = useState(""),
    [draft, setDraft] = useState(""),
    [tab, setTab] = useState("forecast");
  const api = useMemo(() => createClient(token), [token]);
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <Logo />
          <div>
            трамвай<span>ПРОГНОЗ ЗАГРУЗКИ</span>
          </div>
        </div>
        <div className="workspace-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <nav aria-label="Основная навигация">
          {tabs.map(([id, num, name]) => (
            <button
              key={id}
              className={tab === id ? "nav active" : "nav"}
              onClick={() => setTab(id)}
            >
              <span>{num}</span>
              {name}
              {tab === id && <b>↗</b>}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="live-dot" /> Москва · UTC+3
          <p>
            Открытые данные.
            <br />
            Проверяемые расчёты.
          </p>
          <a href="/docs" target="_blank" rel="noreferrer">
            Swagger API ↗
          </a>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <p className="eyebrow">ГОРОДСКАЯ МОБИЛЬНОСТЬ / АНАЛИТИКА</p>
            <h1>{tabs.find((t) => t[0] === tab)[2]} трамвайных маршрутов</h1>
          </div>
          <Badge>v0.1 · research</Badge>
        </header>
        {!token ? (
          <section className="panel login">
            <div className="login-art">
              <Logo />
              <span>
                Город в движении.
                <br />
                Данные в контексте.
              </span>
              <p>
                История, сезонный прогноз и баланс пассажиров в одном рабочем
                пространстве.
              </p>
            </div>
            <div>
              <p className="eyebrow">ПОДКЛЮЧЕНИЕ К API</p>
              <h2>Откройте рабочее пространство</h2>
              <p className="muted">
                Введите ключ viewer для просмотра или operator для создания
                расчётов. Ключ хранится только в памяти вкладки.
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  setToken(draft.trim());
                  setDraft("");
                }}
              >
                <label>
                  Ключ доступа
                  <input
                    type="password"
                    required
                    minLength="32"
                    autoComplete="off"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder="Ключ из локального .env"
                  />
                </label>
                <button>Подключиться →</button>
              </form>
              <small>
                Backend и worker должны быть запущены. Инструкция — в README
                проекта.
              </small>
            </div>
          </section>
        ) : (
          <>
            <div className="session">
              <span>Ключ подключён · данные загружаются из API</span>
              <button className="text-button" onClick={() => setToken("")}>
                Отключиться
              </button>
            </div>
            <Workspace key={token} api={api} tab={tab} />
          </>
        )}
        <footer>
          Трамвай / исследовательский прототип{" "}
          <span>Сезонная база · без обучения моделей</span>
        </footer>
      </main>
    </div>
  );
}

function Workspace({ api, tab }) {
  const caps = useResource(
    (signal) => api.request("/capabilities", { signal }),
    [api],
  );
  const [routeId, setRouteId] = useState("");
  const network = caps.data?.network_revision_id;
  const validAt = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Moscow",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  const routes = useResource(
    (signal) =>
      network
        ? api.all(
            "/routes",
            { network_revision_id: network, valid_at: validAt },
            signal,
          )
        : [],
    [api, network, validAt],
  );
  const selected = routeId || routes.data?.[0]?.id;
  const route = useResource(
    (signal) =>
      selected
        ? api.request("/routes/" + encodeURIComponent(selected), {
            query: { network_revision_id: network, valid_at: validAt },
            signal,
          })
        : null,
    [api, network, selected, validAt],
  );
  if (caps.error || routes.error || route.error)
    return <ErrorBox error={caps.error || routes.error || route.error} />;
  if (caps.loading || routes.loading || route.loading) return <Loading />;
  if (!caps.data || !route.data)
    return (
      <Empty>
        Нет опубликованной маршрутной сети. Подготовьте и опубликуйте набор
        данных.
      </Empty>
    );
  const data = caps.data,
    props = { api, caps: data, route: route.data };
  return (
    <>
      <div className="dataset-bar">
        <label>
          Маршрут
          <select value={selected} onChange={(e) => setRouteId(e.target.value)}>
            {routes.data.map((r) => (
              <option key={r.id} value={r.id}>
                {r.number} · {r.name}
              </option>
            ))}
          </select>
        </label>
        <div>
          <Badge tone={data.source_mode === "demo" ? "amber" : ""}>
            {data.source_mode === "demo"
              ? "Демонстрационные данные"
              : data.source_mode}
          </Badge>
          <small>{data.dataset_revision_id}</small>
        </div>
      </div>
      {data.source_mode === "demo" && (
        <div className="demo-banner">
          <b>ДЕМО</b> Синтетическая маршрутная сеть и пассажиропоток. Результаты
          не описывают реальную загрузку Москвы.
        </div>
      )}
      <Freshness api={api} revision={data.dataset_revision_id} />
      <div key={selected}>
        {tab === "forecast" ? (
          <Forecast {...props} />
        ) : tab === "history" ? (
          <History {...props} />
        ) : tab === "evaluations" ? (
          <Evaluations {...props} />
        ) : tab === "occupancy" ? (
          <Occupancy {...props} />
        ) : (
          <Context {...props} />
        )}
      </div>
    </>
  );
}
