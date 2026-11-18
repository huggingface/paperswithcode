import React from "react";
import { createRoot } from "react-dom/client";
import { ThemeProvider } from "next-themes";

import AppErrorBoundary from "./components/AppErrorBoundary";
import "./styles/fonts.css";
import "./index.css";
import { installChunkReloadRecovery } from "./lib/chunkReload";
import { initPostHog } from "./lib/posthog";
import "./styles.css";
import "./styles/features/index.css";
import "./components/chat/styles/index.css";
import App from "./App";

installChunkReloadRecovery();
initPostHog(import.meta.env.VITE_POSTHOG_PROJECT_TOKEN);

const app = (
  <ThemeProvider
    attribute="class"
    defaultTheme="system"
    enableSystem
    disableTransitionOnChange
    storageKey="pwc-theme"
  >
    <AppErrorBoundary>
      <App />
    </AppErrorBoundary>
  </ThemeProvider>
);

const root = createRoot(document.getElementById("root")!);
root.render(
  <React.StrictMode>
    {app}
  </React.StrictMode>,
);
