import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";
import { createAnalyticsRouterWindow, loadCloudflareAnalytics } from "./analytics";

const routerWindow = createAnalyticsRouterWindow(window, import.meta.env.PROD);
loadCloudflareAnalytics(window, import.meta.env.PROD);

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter window={routerWindow}>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
