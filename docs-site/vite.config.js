import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// `VITE_DOCS_BASE` lets the same build serve at the dev server's root (`/`) and
// under the deployed landing page at `/docs/`. Cloudflare Pages serves the docs
// from a sub-path of the one project, so `deploy/` sets it to `/docs/`; local
// `npm run dev` leaves it unset and the site stays at the origin root.
export default defineConfig({
  base: process.env.VITE_DOCS_BASE || "/",
  plugins: [react(), tailwindcss()],
  server: {
    port: 5174,
  },
  build: {
    outDir: "dist",
  },
});
