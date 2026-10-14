import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { flatNav } from "../nav.js";
import { docs } from "../content/registry.js";
import ContextForgeMark from "./ContextForgeMark.jsx";

function buildIndex() {
  return flatNav.map((item) => {
    const body = docs[item.slug]?.body || "";
    return {
      slug: item.slug,
      title: item.title,
      group: item.group,
      haystack: `${item.title} ${item.group} ${body}`.toLowerCase(),
    };
  });
}

export default function TopBar() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const inputRef = useRef(null);
  const index = useRef(buildIndex());

  useEffect(() => {
    function onKey(e) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const results = query.trim()
    ? index.current
        .filter((item) => item.haystack.includes(query.toLowerCase()))
        .slice(0, 8)
    : flatNav.slice(0, 8);

  function go(slug) {
    setOpen(false);
    setQuery("");
    navigate(slug === "index" ? "/" : `/${slug}`);
  }

  return (
    <>
      <header className="sticky top-0 z-40 h-14 border-b border-line bg-canvas/80 backdrop-blur">
        <div className="mx-auto flex h-full max-w-[100rem] items-center gap-4 px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-2.5">
            <ContextForgeMark size={24} />
            <span className="font-semibold text-ink">
              Context<span className="text-brand">Forge</span>
            </span>
            <span className="text-faint">Docs</span>
          </Link>

          <div className="ml-auto flex items-center gap-2.5">
            <button
              onClick={() => setOpen(true)}
              className="flex h-9 items-center gap-2 rounded-full border border-line-strong bg-surface px-4 text-sm font-semibold text-muted transition-colors hover:text-ink"
            >
              <svg
                className="h-3.5 w-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <circle cx="11" cy="11" r="7" />
                <path d="m21 21-4.3-4.3" />
              </svg>
              <span className="hidden sm:inline">Search</span>
              <kbd className="hidden rounded border border-line-strong px-1.5 text-[10px] sm:inline">
                ⌘K
              </kbd>
            </button>
            <a
              href="https://github.com/AdnanZamanNiloy/contexforge"
              target="_blank"
              rel="noreferrer"
              className="hidden h-9 items-center rounded-full border border-line-strong bg-surface px-4 text-sm font-semibold text-muted transition-colors hover:text-ink sm:inline-flex"
            >
              GitHub
            </a>
          </div>
        </div>
      </header>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-overlay p-4 pt-[12vh] backdrop-blur-sm"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-xl overflow-hidden rounded-xl border border-line-strong bg-surface shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 border-b border-line-strong px-4">
              <svg
                className="h-4 w-4 text-faint"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <circle cx="11" cy="11" r="7" />
                <path d="m21 21-4.3-4.3" />
              </svg>
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search documentation…"
                className="w-full bg-transparent py-3.5 text-sm text-ink outline-none placeholder:text-faint"
              />
            </div>
            <ul className="max-h-80 overflow-y-auto p-2">
              {results.length === 0 && (
                <li className="px-3 py-6 text-center text-sm text-faint">
                  No results for “{query}”.
                </li>
              )}
              {results.map((item) => (
                <li key={item.slug}>
                  <button
                    onClick={() => go(item.slug)}
                    className="flex w-full flex-col items-start rounded-md px-3 py-2 text-left transition-colors hover:bg-elevated"
                  >
                    <span className="text-sm text-ink">{item.title}</span>
                    <span className="text-xs text-faint">{item.group}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}
