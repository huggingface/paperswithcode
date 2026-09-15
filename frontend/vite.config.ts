import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import fs from "fs";

// Prod dev server runs on :8080; staging runs on :8081.
// For DNS-backed staging, set VITE_HMR_HOST / VITE_HMR_PROTOCOL / VITE_HMR_CLIENT_PORT.
// Without those env vars, Vite uses the browser's current origin, which keeps raw-IP
// previews like http://167.235.148.241:8081 from reconnecting to the wrong HMR host.
export default defineConfig(({ mode }) => {
  const isStaging = mode === "staging";
  const env = loadEnv(mode, process.cwd(), "");
  const chatEnabled = ["1", "true", "yes"].includes(
    String(process.env.VITE_CHAT_ENABLED ?? env.VITE_CHAT_ENABLED ?? "")
      .trim()
      .toLowerCase(),
  );
  const mcpAppsHostEnabled = ["1", "true", "yes"].includes(
    String(process.env.VITE_CHAT_MCP_APPS_HOST_ENABLED ?? env.VITE_CHAT_MCP_APPS_HOST_ENABLED ?? "").trim().toLowerCase(),
  );
  const nativePdfReaderEnabled = ["1", "true", "yes"].includes(
    String(process.env.VITE_NATIVE_PDF_READER_ENABLED ?? env.VITE_NATIVE_PDF_READER_ENABLED ?? "")
      .trim()
      .toLowerCase(),
  );
  const paperReaderChatEnabled = ["1", "true", "yes"].includes(
    String(process.env.VITE_PAPER_READER_CHAT_ENABLED ?? env.VITE_PAPER_READER_CHAT_ENABLED ?? "")
      .trim()
      .toLowerCase(),
  );
  const paperReaderSelectionEnabled = ["1", "true", "yes"].includes(
    String(process.env.VITE_PAPER_READER_SELECTION_ENABLED ?? env.VITE_PAPER_READER_SELECTION_ENABLED ?? "")
      .trim()
      .toLowerCase(),
  );
  const codexAddEvalsEnabled = ["1", "true", "yes"].includes(
    String(process.env.VITE_CODEX_ADD_EVALS_ENABLED ?? env.VITE_CODEX_ADD_EVALS_ENABLED ?? "")
      .trim()
      .toLowerCase(),
  );
  const codexEnrichPaperEnabled = ["1", "true", "yes"].includes(
    String(process.env.VITE_CODEX_ENRICH_PAPER_ENABLED ?? env.VITE_CODEX_ENRICH_PAPER_ENABLED ?? "")
      .trim()
      .toLowerCase(),
  );
  const hmrHost = env.VITE_HMR_HOST;
  const hmrProtocol = env.VITE_HMR_PROTOCOL as "ws" | "wss" | undefined;
  const hmrClientPort = env.VITE_HMR_CLIENT_PORT
    ? Number(env.VITE_HMR_CLIENT_PORT)
    : undefined;
  const hmr = hmrHost
    ? {
        host: hmrHost,
        ...(hmrProtocol ? { protocol: hmrProtocol } : {}),
        ...(hmrClientPort ? { clientPort: hmrClientPort } : {}),
      }
    : undefined;

  const proxy = {
    "/api": {
      target: isStaging ? "http://127.0.0.1:8001" : "http://127.0.0.1:8000",
      changeOrigin: true,
      secure: false,
    },
  };

  return {
    define: { "import.meta.env.VITE_CHAT_MCP_APPS_HOST_ENABLED": JSON.stringify(mcpAppsHostEnabled ? "true" : "false") },
    build: {
      rollupOptions: {
        output: {
          assetFileNames: (assetInfo) => assetInfo.name === "pdf.worker.min.mjs"
            ? "assets/pdf.worker.min-[hash].js"
            : "assets/[name]-[hash][extname]",
        },
      },
    },
    server: {
      host: "::",
      port: isStaging ? 8081 : 8080,
      strictPort: true,
      allowedHosts: isStaging
        ? [
            "staging.paperswithcode.co",
            "167.235.148.241",
            // Tailnet-only preview (ufw opens 8081 on tailscale0 only)
            "100.107.126.51",
            "paperswithcode-vps.taildb5d.ts.net",
          ]
        : ["paperswithcode.co", "www.paperswithcode.co"],
      ...(hmr ? { hmr } : {}),
      proxy,
    },
    preview: {
      host: "::",
      port: isStaging ? 8081 : 8080,
      strictPort: true,
      allowedHosts: isStaging
        ? ["staging.paperswithcode.co", "167.235.148.241"]
        : ["paperswithcode.co", "www.paperswithcode.co", "167.235.148.241"],
      proxy,
    },
    plugins: [
      react(),
      {
        name: "pwc-feature-manifest",
        writeBundle() {
          fs.writeFileSync(
            path.resolve(__dirname, "dist/features.json"),
            `${JSON.stringify({
              chat: chatEnabled,
              native_pdf_reader: nativePdfReaderEnabled,
              paper_reader_chat: paperReaderChatEnabled,
              paper_reader_selection: paperReaderSelectionEnabled,
              codex_add_evals: codexAddEvalsEnabled,
              codex_enrich_paper: codexEnrichPaperEnabled,
            }, null, 2)}\n`,
          );
        },
      },
    ],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
  };
});
