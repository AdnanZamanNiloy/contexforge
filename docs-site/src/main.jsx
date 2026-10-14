import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import "./index.css";

// Matches `base` in vite.config.js. Vite sets `import.meta.env.BASE_URL` from
// that option (trailing slash included), so the router's basename and the
// asset paths can never disagree — bare `/` locally, `/docs/` when deployed
// under the landing page.
const basename = import.meta.env.BASE_URL.replace(/\/$/, "");

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter basename={basename}>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
