import React from "react";
import { createRoot } from "react-dom/client";
import { ThemeProvider } from "next-themes";
import { PostHogProvider } from "@posthog/react";

import AppErrorBoundary from "./components/AppErrorBoundary";
import "./index.css";
import { installChunkReloadRecovery } from "./lib/chunkReload";
import { posthogPrivacyOptions } from "./lib/posthogPrivacy";
import "./styles.css";
import "./styles/features/index.css";
import "./components/chat/styles/index.css";
import App from "./App";

installChunkReloadRecovery();

const posthogToken = import.meta.env.VITE_POSTHOG_PROJECT_TOKEN;

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
    {posthogToken ? (
      <PostHogProvider apiKey={posthogToken} options={posthogPrivacyOptions}>
        {app}
      </PostHogProvider>
    ) : app}
  </React.StrictMode>,
);
