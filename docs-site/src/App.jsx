import { useState } from "react";
import { Routes, Route, Navigate, Link, useParams } from "react-router-dom";
import TopBar from "./components/TopBar.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Markdown from "./components/Markdown.jsx";
import { docs, docList } from "./content/registry.js";

function DocPage() {
  const { slug } = useParams();
  const key = slug || "index";
  const doc = docs[key];
  if (!doc) return <Navigate to="/" replace />;

  const idx = docList.findIndex((d) => d.slug === key);
  const prev = idx > 0 ? docList[idx - 1] : null;
  const next = idx < docList.length - 1 ? docList[idx + 1] : null;

  return (
    <div className="px-6 py-10 sm:px-10">
      {doc.group !== "Start here" && (
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand">
          {doc.group}
        </p>
      )}
      <Markdown body={doc.body} />
      <div className="mt-16 flex max-w-[46rem] items-stretch justify-between gap-4 border-t border-line pt-6">
        {prev ? (
          <Link
            to={prev.slug === "index" ? "/" : `/${prev.slug}`}
            className="group flex-1 rounded-lg border border-line p-4 transition-colors hover:border-line-strong"
          >
            <span className="text-xs text-faint">Previous</span>
            <span className="block text-sm text-ink group-hover:text-brand">
              {prev.title}
            </span>
          </Link>
        ) : (
          <span className="flex-1" />
        )}
        {next ? (
          <Link
            to={next.slug === "index" ? "/" : `/${next.slug}`}
            className="group flex-1 rounded-lg border border-line p-4 text-right transition-colors hover:border-line-strong"
          >
            <span className="text-xs text-faint">Next</span>
            <span className="block text-sm text-ink group-hover:text-brand">
              {next.title}
            </span>
          </Link>
        ) : (
          <span className="flex-1" />
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <>
      <TopBar />
      <div className="mx-auto flex max-w-[100rem]">
        <Sidebar
          open={sidebarOpen}
          onNavigate={() => setSidebarOpen(false)}
        />
        <button
          onClick={() => setSidebarOpen((v) => !v)}
          className="fixed bottom-6 right-6 z-30 rounded-full border border-line-strong bg-elevated px-4 py-2 text-sm text-ink shadow-lg lg:hidden"
        >
          {sidebarOpen ? "Close" : "Menu"}
        </button>
        <main className="min-w-0 flex-1">
          <Routes>
            <Route path="/" element={<DocPage />} />
            <Route path="/:slug" element={<DocPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </>
  );
}
