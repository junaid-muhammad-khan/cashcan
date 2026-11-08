import { useEffect, useState } from "react";
import { api } from "./api.js";
import Login from "./pages/Login.jsx";
import Onboarding from "./pages/Onboarding.jsx";
import Dashboard from "./pages/Dashboard.jsx";

export default function App() {
  const [me, setMe] = useState(null); // null = loading

  const refresh = () => api("/me").then(setMe).catch(() => setMe({ authenticated: false }));
  useEffect(() => { refresh(); }, []);

  if (!me) return <div className="center muted">Loading…</div>;
  if (!me.authenticated) return <Login info={me} />;

  const patch = (p) => setMe((m) => ({ ...m, ...p }));

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">CashCan</div>
        <div className="topbar-right">
          <span className="muted">{me.user.display_name}</span>
          <a className="btn ghost" href="/auth/logout">Sign out</a>
        </div>
      </header>
      <main>
        {me.onboarding.complete
          ? <Dashboard me={me} />
          : <Onboarding me={me} onChange={patch} />}
      </main>
    </div>
  );
}
