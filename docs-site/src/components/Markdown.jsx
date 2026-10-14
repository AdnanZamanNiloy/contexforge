import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";

function heading(Tag) {
  return function Heading({ children, id }) {
    return (
      <Tag id={id} className="group">
        {id ? (
          <a href={`#${id}`} className="header-anchor">
            {children}
          </a>
        ) : (
          children
        )}
      </Tag>
    );
  };
}

const components = {
  h1: heading("h1"),
  h2: heading("h2"),
  h3: heading("h3"),
  h4: heading("h4"),
};

function extractHeadings(body) {
  const lines = body.split("\n");
  const out = [];
  let inFence = false;
  let i = 0;
  for (const line of lines) {
    if (line.trimStart().startsWith("```")) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;
    const m = /^(#{2,3})\s+(.*)$/.exec(line);
    if (m) {
      out.push({ depth: m[1].length, text: m[2].replace(/[`*]/g, "") });
    }
  }
  return out;
}

function OnThisPage({ body }) {
  const headings = useMemo(() => extractHeadings(body), [body]);
  const [active, setActive] = useState("");

  useEffect(() => {
    const ids = headings.map((h) =>
      h.text
        .toLowerCase()
        .replace(/[^\w\s-]/g, "")
        .trim()
        .replace(/\s+/g, "-"),
    );
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(entry.target.id);
        }
      },
      { rootMargin: "-80px 0px -70% 0px" },
    );
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [headings]);

  if (headings.length < 2) return null;

  return (
    <nav className="hidden xl:block w-56 shrink-0 pt-10">
      <div className="sticky top-24">
        <p className="text-xs font-semibold uppercase tracking-wider text-faint mb-3">
          On this page
        </p>
        <ul className="space-y-1.5 border-l border-line-strong pl-3">
          {headings.map((h) => {
            const id = h.text
              .toLowerCase()
              .replace(/[^\w\s-]/g, "")
              .trim()
              .replace(/\s+/g, "-");
            return (
              <li key={id} style={{ paddingLeft: h.depth === 3 ? 10 : 0 }}>
                <a
                  href={`#${id}`}
                  className={`block text-sm transition-colors ${
                    active === id
                      ? "text-brand"
                      : "text-faint hover:text-ink"
                  }`}
                >
                  {h.text}
                </a>
              </li>
            );
          })}
        </ul>
      </div>
    </nav>
  );
}

export default function Markdown({ body }) {
  return (
    <div className="flex gap-10">
      <article className="prose-docs min-w-0 flex-1 max-w-[46rem]">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeSlug]}
          components={components}
        >
          {body}
        </ReactMarkdown>
      </article>
      <OnThisPage body={body} />
    </div>
  );
}
