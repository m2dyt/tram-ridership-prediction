import React, { useState, useEffect, useMemo } from "react";
import { Routes, Route, NavLink, useNavigate, useLocation } from "react-router-dom";
import { updateToken, subscribeToken, getToken } from "./api/tokenBus";
import MapPage from "./pages/MapPage";
import DashboardPage from "./pages/DashboardPage";
import ModelsPage from "./pages/ModelsPage";
import { createClient } from "./api/client";
import { ErrorBox, Loading, Empty, Badge, Freshness } from "./components/Common";
import { useCapabilities, useRoutes, useRoute, useLogin, useRegister, useLogout, useMe } from "./api/hooks";
import Forecast from "./features/Forecast";
import History from "./features/History";
import Evaluations from "./features/Evaluations";
import Occupancy from "./features/Occupancy";
import Context from "./features/Context";


const NAV_ITEMS = [
  { to: "/", label: "Карта маршрутов", icon: "/icons/geo_icon.svg" },
  { to: "/dashboard", label: "Дашборд", icon: "/icons/Column_graphs.svg" },
  { to: "/forecast", label: "Прогноз", icon: "/icons/signal_icon.svg" },
  { to: "/history", label: "История", icon: "/icons/Circles_graphs.svg" },
  { to: "/evaluations", label: "Качество", icon: "/icons/camera_icon.svg" },
  { to: "/occupancy", label: "Наполненность", icon: "/icons/occupancy_icon.svg" },
  { to: "/context", label: "Контекст", icon: "/icons/geo_icon.svg" },
  { to: "/models", label: "Модели", icon: "/icons/Circles_graphs.svg" },
];

function BrandCard() {
  return (
    <div className="mgt-brand-card">
      <div className="brand-logo-area">
        <img src="/icons/MGT_logo_ru_white.svg" alt="Мосгортранс" className="mgt-logo-img" />
      </div>
      <div className="brand-meta-badge">
        <span className="brand-tag">МОДЕЛИРОВАНИЕ И АНАЛИТИКА</span>
      </div>
    </div>
  );
}

function LoginPage() {
  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [isRegistering, setIsRegistering] = React.useState(false);

  const loginMutation = useLogin();
  const registerMutation = useRegister();

  const handleAuth = (e) => {
    e.preventDefault();
    if (isRegistering) {
      registerMutation.mutate({ username, password }, {
        onSuccess: () => {
          loginMutation.mutate({ username, password });
        }
      });
    } else {
      loginMutation.mutate({ username, password });
    }
  };

  return (
    <div className="login-page-container">
      <section className="login-card">
        <div className="login-art">
          <div className="login-art-uzor" />
          <div className="login-art-inner">
            <img src="/icons/MGT_logo_ru_white.svg" alt="Мосгортранс" className="login-brand-logo" />
            
            <div className="login-tagline">
              Город в движении.<br />
              <span>Данные в контексте.</span>
            </div>

            <p className="login-desc">
              Служебная аналитическая платформа мониторинга и прогнозирования пассажиропотока трамвайной сети Москвы.
            </p>

            <div className="login-features-list">
              <div className="login-feature-item">
                <img src="/icons/geo_icon.svg" alt="" className="login-feature-icon" />
                <span>Маршруты и остановочные пункты Москвы</span>
              </div>
              <div className="login-feature-item">
                <img src="/icons/signal_icon.svg" alt="" className="login-feature-icon" />
                <span>ML-прогнозирование суточного потока</span>
              </div>
              <div className="login-feature-item">
                <img src="/icons/camera_icon.svg" alt="" className="login-feature-icon" />
                <span>Мониторинг качества и наполненности</span>
              </div>
            </div>

            <div className="login-art-caption">
              Департамент транспорта Москвы · ГУП «Мосгортранс»
            </div>
          </div>
        </div>

        <div className="login-form-side">
          <div className="login-form-header">
            <p className="eyebrow">СЛУЖЕБНЫЙ ДОСТУП К ДАННЫМ</p>
            <h2>{isRegistering ? "Создание учётной записи" : "Вход в систему"}</h2>
            <p className="login-lead-text">
              {isRegistering
                ? "Новая учётная запись получает роль просмотра. Общий оператор operator создаётся миграцией и при каждом запуске Docker."
                : "Общий оператор для локального стенда: логин operator, пароль — в docs/DOCKER_STACK.md."}
            </p>
          </div>

          <form onSubmit={handleAuth} className="mgt-form">
            <label>
              Имя пользователя
              <input
                type="text"
                required
                placeholder="например, admin"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </label>
            <label>
              Пароль
              <input
                type="password"
                required
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {loginMutation.isError && <div className="notice error">Ошибка входа: {loginMutation.error.message}</div>}
            {registerMutation.isError && <div className="notice error">Ошибка регистрации: {registerMutation.error.message}</div>}
            <button type="submit" className="mgt-submit-btn" disabled={loginMutation.isPending || registerMutation.isPending}>
                {isRegistering ? "Создать учётную запись" : "Войти в систему"} →
            </button>
            <div className="login-sub-actions">
              <a href="#" onClick={(e) => { e.preventDefault(); setIsRegistering(!isRegistering); }}>
                {isRegistering ? "Уже есть учётная запись? Войти" : "Создать новую учётную запись"}
              </a>
            </div>
          </form>
        </div>
      </section>
    </div>
  );
}

export default function App() {
  const [token, setToken] = React.useState(getToken() || "");
  
  React.useEffect(() => {
    return subscribeToken(setToken);
  }, []);

  const api = React.useMemo(() => (token ? createClient(token) : null), [token]);

  if (!token) {
    return <LoginPage />;
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <BrandCard />
        <div className="workspace-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <nav aria-label="Основная навигация">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => "nav " + (isActive ? "active" : "")}
            >
              <img src={item.icon} alt="" className="nav-icon" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-clock"><span className="live-dot" /> Москва · UTC+3</div>
          <UserBadge />
        </div>
      </aside>

      <main>
        <Workspace key={token} />
      </main>
    </div>
  );
}

function UserBadge() {
  const { data: user, isLoading } = useMe();
  const logoutMutation = useLogout();

  if (isLoading) return <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Загрузка профиля...</div>;
  if (!user) return null;

  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.85rem', padding: '6px 8px', background: 'var(--bg-panel)', borderRadius: '6px' }}>
      <span style={{ fontWeight: 500, color: 'var(--text)' }}>
        {user.username} <span style={{ color: 'var(--text-muted)' }}>({user.role})</span>
      </span>
      <button 
        className="secondary" 
        style={{ padding: '2px 8px', fontSize: '0.8rem', height: 'auto', minHeight: 'auto' }} 
        onClick={() => logoutMutation.mutate()}
        disabled={logoutMutation.isPending}
      >
        Выйти
      </button>
    </div>
  );
}

function Workspace() {
  const capsQuery = useCapabilities();
  const caps = { data: capsQuery.data, loading: capsQuery.isLoading, error: capsQuery.error };
  
  const [routeId, setRouteId] = useState("");
  const network = caps.data?.network_revision_id;
  const validAt = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Moscow",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());

  const routesQuery = useRoutes(network, validAt);
  const routes = { data: routesQuery.data, loading: routesQuery.isLoading, error: routesQuery.error };
  const rawRoutes = routes.data || [];

  const allRoutes = useMemo(() => {
    return [...rawRoutes].sort((a, b) => {
      const na = parseInt(a.number, 10);
      const nb = parseInt(b.number, 10);
      if (!isNaN(na) && !isNaN(nb)) return na - nb;
      return (a.number || "").localeCompare(b.number || "");
    });
  }, [rawRoutes]);

  const selected = routeId || allRoutes[0]?.id;
  const routeQuery = useRoute(selected, network, validAt);
  const route = { data: routeQuery.data, loading: routeQuery.isLoading, error: routeQuery.error };

  const location = useLocation();

  const [showFreshness, setShowFreshness] = useState(false);

  if (caps.error || routes.error || route.error)
    return <ErrorBox error={caps.error || routes.error || route.error} />;
  
  if (caps.loading || routes.loading || route.loading) return <Loading />;
  
  if (!caps.data || !route.data)
    return (
      <Empty>
        API не вернул опубликованные маршруты. Запустите импорт реального набора данных.
      </Empty>
    );

  const data = caps.data;
  const props = { caps: data, route: route.data };
  
  const titles = {
    "/": "Карта маршрутов",
    "/dashboard": "Дашборд",
    "/forecast": "Прогноз",
    "/history": "История",
    "/evaluations": "Качество",
    "/occupancy": "Наполненность",
    "/context": "Контекст",
    "/models": "Модели"
  };
  const title = titles[location.pathname] || "Обзор";

  return (
    <>
      <header>
        <div>
          <p className="eyebrow">ГОРОДСКАЯ МОБИЛЬНОСТЬ / АНАЛИТИКА</p>
          <h1>{title === "Карта маршрутов" ? "Карта трамвайных маршрутов" : `${title} трамвайных маршрутов`}</h1>
        </div>
        <Badge>v0.1 · research</Badge>
      </header>

      <div className="mgt-uzor-header-strip" aria-hidden="true" />
      
      <div className="modern-toolbar">
        <div className="route-picker-section">
          <span className="route-picker-label">Маршрут:</span>
          <div className="route-chips-row">
            {allRoutes.map((r) => {
              const isActive = selected === r.id;
              return (
                <button
                  key={r.id}
                  type="button"
                  className={`tram-chip ${isActive ? "active" : ""}`}
                  onClick={() => setRouteId(r.id)}
                  title={`Выбрать маршрут ${r.number}`}
                >
                  {r.number}
                </button>
              );
            })}
          </div>
        </div>

        <div className="toolbar-status-group">
          {data.source_mode === "demo" && (
            <div className="status-badge-demo" title="Синтетическая маршрутная сеть и поток. Не описывает реальную загрузку Москвы.">
              <span className="demo-dot"></span>
              <span>Демо-режим</span>
            </div>
          )}

          <button
            type="button"
            className={`freshness-toggle-btn ${showFreshness ? "active" : ""}`}
            onClick={() => setShowFreshness(v => !v)}
            title="Показать информацию об источниках данных"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
            <span>Источники данных</span>
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{
                transform: showFreshness ? "rotate(180deg)" : "none",
                transition: "transform 0.2s ease"
              }}
            >
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>
        </div>
      </div>
      
      {showFreshness && (
        <div className="freshness-popdown">
          <Freshness revision={data.dataset_revision_id} />
        </div>
      )}
      
      <div key={selected} style={{ marginTop: "1rem" }}>
        <Routes>
          <Route path="/" element={<MapPage route={route.data} caps={data} />} />
          <Route path="/dashboard" element={<DashboardPage caps={data} route={route.data} />} />
          <Route path="/forecast" element={<Forecast {...props} />} />
          <Route path="/history" element={<History {...props} />} />
          <Route path="/evaluations" element={<Evaluations {...props} />} />
          <Route path="/occupancy" element={<Occupancy {...props} />} />
          <Route path="/context" element={<Context {...props} />} />
          <Route path="/models" element={<ModelsPage />} />
        </Routes>
      </div>
    </>
  );
}
