import React, { useState, useEffect } from "react";
import { Routes, Route, NavLink, useNavigate, useLocation } from "react-router-dom";
import { updateToken, subscribeToken } from "./api/tokenBus";
import MapPage from "./pages/MapPage";
import DashboardPage from "./pages/DashboardPage";
import { createClient } from "./api/client";
import { ErrorBox, Loading, Empty, Badge, Freshness, useResource } from "./components/Common";
import Forecast from "./features/Forecast";
import History from "./features/History";
import Evaluations from "./features/Evaluations";
import Occupancy from "./features/Occupancy";
import Context from "./features/Context";

function Logo() {
  return (
    <span className="logo-icon">
      <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <path d="M10 3h12M16 3v4M9 25l-3 5m17-5 3 5M8 14h16" stroke="currentColor" strokeWidth="2" />
        <rect x="7" y="7" width="18" height="19" rx="5" stroke="currentColor" strokeWidth="2" />
        <circle cx="11" cy="21" r="1.5" fill="currentColor" />
        <circle cx="21" cy="21" r="1.5" fill="currentColor" />
      </svg>
    </span>
  );
}

export default function App() {
  const [token, setToken] = React.useState("");
  const [draft, setDraft] = React.useState("");
  
  React.useEffect(() => {
    return subscribeToken(setToken);
  }, []);

  const api = React.useMemo(() => (token ? createClient(token) : null), [token]);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <Logo />
          <div>
            МосТранс<span>ПРОГНОЗ</span>
          </div>
        </div>
        <div className="workspace-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <nav aria-label="Основная навигация">
           <NavLink to="/" className={({ isActive }) => "nav " + (isActive ? "active" : "")}>
             <span>00</span> Карта маршрутов 
           </NavLink>
           <NavLink to="/dashboard" className={({ isActive }) => "nav " + (isActive ? "active" : "")}>
             <span>01</span> Дашборд
           </NavLink>
           <NavLink to="/forecast" className={({ isActive }) => "nav " + (isActive ? "active" : "")}>
             <span>02</span> Прогноз
           </NavLink>
           <NavLink to="/history" className={({ isActive }) => "nav " + (isActive ? "active" : "")}>
             <span>03</span> История
           </NavLink>
           <NavLink to="/evaluations" className={({ isActive }) => "nav " + (isActive ? "active" : "")}>
             <span>04</span> Качество
           </NavLink>
           <NavLink to="/occupancy" className={({ isActive }) => "nav " + (isActive ? "active" : "")}>
             <span>05</span> Наполненность
           </NavLink>
           <NavLink to="/context" className={({ isActive }) => "nav " + (isActive ? "active" : "")}>
             <span>06</span> Контекст
           </NavLink>
        </nav>
        <div className="sidebar-footer">
          <span className="live-dot" /> Москва · UTC+3
        </div>
      </aside>

      <main>
        {!token ? (
           <section className="panel login">
            <div className="login-art">
              <Logo />
              <span>
                Город в движении.<br />Данные в контексте.
              </span>
            </div>
            <div>
              <p className="eyebrow">ПОДКЛЮЧЕНИЕ К API</p>
              <h2>Откройте рабочее пространство</h2>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  updateToken(draft.trim());
                  setDraft("");
                }}
              >
                <label>
                  Ключ доступа
                  <input
                    type="password"
                    required
                    minLength="1"
                    autoComplete="off"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder="Ключ из локального .env"
                  />
                </label>
                <button type="submit">Подключиться →</button>
              </form>
            </div>
          </section>
        ) : (
          <Workspace key={token} api={api} />
        )}
      </main>
    </div>
  );
}

function Workspace({ api }) {
  const caps = useResource(
    (signal) => api.request("/capabilities", { signal }),
    [api]
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
            signal
          )
        : [],
    [api, network, validAt]
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
    [api, network, selected, validAt]
  );

  const location = useLocation();

  if (caps.error || routes.error || route.error)
    return <ErrorBox error={caps.error || routes.error || route.error} />;
  
  if (caps.loading || routes.loading || route.loading) return <Loading />;
  
  if (!caps.data || !route.data)
    return (
      <Empty>
        Нет опубликованной маршрутной сети. Подготовьте и опубликуйте набор данных.
      </Empty>
    );

  const data = caps.data;
  const props = { api, caps: data, route: route.data };
  
  const titles = {
    "/": "Карта маршрутов",
    "/dashboard": "Дашборд",
    "/forecast": "Прогноз",
    "/history": "История",
    "/evaluations": "Качество",
    "/occupancy": "Наполненность",
    "/context": "Контекст"
  };
  const title = titles[location.pathname] || "Обзор";

  return (
    <>
      <header>
        <div>
          <p className="eyebrow">ГОРОДСКАЯ МОБИЛЬНОСТЬ / АНАЛИТИКА</p>
          <h1>{title} трамвайных маршрутов</h1>
        </div>
        <Badge>v0.1 · research</Badge>
      </header>
      
      <div className="dataset-bar">
        <label>
          Выбранный маршрут
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
          <b>ДЕМО</b> Синтетическая маршрутная сеть и пассажиропоток. Результаты не описывают реальную загрузку Москвы.
        </div>
      )}
      
      <Freshness api={api} revision={data.dataset_revision_id} />
      
      <div key={selected} style={{ marginTop: "1rem" }}>
        <Routes>
          <Route path="/" element={<MapPage route={route.data} />} />
          <Route path="/dashboard" element={<DashboardPage caps={data} />} />
          <Route path="/forecast" element={<Forecast {...props} />} />
          <Route path="/history" element={<History {...props} />} />
          <Route path="/evaluations" element={<Evaluations {...props} />} />
          <Route path="/occupancy" element={<Occupancy {...props} />} />
          <Route path="/context" element={<Context {...props} />} />
        </Routes>
      </div>
    </>
  );
}
