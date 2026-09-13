import { Link, NavLink, Outlet } from "react-router-dom";
import { useLiveUpdates } from "../api/live";

export default function Layout() {
  useLiveUpdates();
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center gap-6">
          <Link to="/workflows" className="text-brand-500 font-bold text-lg tracking-tight">
            Geotriage
          </Link>
          <nav className="flex gap-4 text-sm">
            {[
              { to: "/workflows", label: "Workflows" },
              { to: "/models", label: "Models" },
              { to: "/providers", label: "Providers" },
              { to: "/infra", label: "Infra" },
            ].map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  isActive ? "text-gray-900" : "text-gray-600 hover:text-gray-800"
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
