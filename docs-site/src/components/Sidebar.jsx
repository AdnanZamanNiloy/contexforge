import { NavLink } from "react-router-dom";
import { nav } from "../nav.js";

export default function Sidebar({ open, onNavigate }) {
  return (
    <aside
      className={`${
        open ? "block" : "hidden"
      } lg:block fixed lg:sticky top-0 lg:top-14 z-30 h-[calc(100vh-3.5rem)] w-72 shrink-0 overflow-y-auto border-r border-line bg-canvas px-6 pb-16 pt-6`}
    >
      {nav.map((group) => (
        <div key={group.title} className="mb-6">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
            {group.title}
          </p>
          <ul className="space-y-0.5">
            {group.items.map((item) => (
              <li key={item.slug}>
                <NavLink
                  to={
                    item.slug === "index" ? "/" : `/${item.slug}`
                  }
                  end={item.slug === "index"}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    `block rounded-md px-3 py-1.5 text-sm transition-colors ${
                      isActive
                        ? "bg-elevated font-medium text-brand"
                        : "text-muted hover:bg-surface hover:text-ink"
                    }`
                  }
                >
                  {item.title}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </aside>
  );
}
