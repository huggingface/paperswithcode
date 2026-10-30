/**
 * Shared helper for resolving the backend API origin.
 *
 * The production frontend served from `paperswithcode.co` calls a same-origin
 * API (the FastAPI process behind the same nginx). The Hugging Face Space
 * mirror is built with `VITE_API_URL` pointing at the production backend so it
 * can browse the same data without shipping a backend.
 *
 * Rules:
 *  - When `VITE_API_URL` is unset, every helper returns relative paths so the
 *    behaviour is identical to today (`fetch("/api/v1/...")`).
 *  - When `VITE_API_URL` is set (e.g. `https://paperswithcode.co`), every API
 *    fetch is prefixed with that origin so the Space frontend talks to the
 *    real backend.
 *  - `isAuthDisabled()` is true when the build sets `VITE_DISABLE_AUTH=1`.
 *    The Space mirror sets this because the HF OAuth cookie can only be set
 *    on the API origin, not the Space origin, so sign-in / bookmarks / cron
 *    dashboard are read-only there.
 *  - `shouldUseHashRouter()` is controlled separately by
 *    `VITE_USE_HASH_ROUTER=1`, so setting a remote API origin does not
 *    accidentally put the canonical site behind `/#/...` URLs.
 */

const stripTrailingSlash = (value: string): string =>
  value.endsWith("/") ? value.slice(0, -1) : value;

function enabledBuildFlag(value: unknown): boolean {
  return ["1", "true", "yes"].includes(String(value ?? "").trim().toLowerCase());
}

/**
 * Returns the API origin (scheme+host[:port]) the frontend should target.
 * Empty string means "same origin as the page" — preserved behaviour for
 * the canonical `paperswithcode.co` deployment.
 */
export function getApiOrigin(): string {
  const raw = import.meta.env.VITE_API_URL?.trim();
  if (!raw) return "";

  try {
    const parsed = raw.startsWith("http")
      ? new URL(raw)
      : new URL(
          raw,
          typeof window !== "undefined"
            ? window.location.origin
            : "http://localhost",
        );
    return stripTrailingSlash(parsed.origin);
  } catch {
    return stripTrailingSlash(raw);
  }
}

/**
 * Build a full URL for the given API path. `path` should start with `/`.
 * When no API origin is configured, the leading slash keeps it same-origin.
 */
export function apiUrl(path: string): string {
  const normalised = path.startsWith("/") ? path : `/${path}`;
  const origin = getApiOrigin();
  return origin ? `${origin}${normalised}` : normalised;
}

/** Build an auth URL, optionally targeting the canonical session authority. */
export function authUrl(path: string): string {
  const normalised = path.startsWith("/") ? path : `/${path}`;
  const raw = import.meta.env.VITE_AUTH_URL?.trim();
  if (!raw) return apiUrl(normalised);
  return `${stripTrailingSlash(raw)}${normalised}`;
}

export interface HfLoginOptions {
  authorizeInference?: boolean;
  collectEmail?: boolean;
  authorizeBucket?: boolean;
  bucketCreate?: boolean;
}

/**
 * Start Hugging Face sign-in and come back to `returnTo` (a path or URL).
 * A cross-origin auth authority gets an absolute return URL; a same-origin
 * one gets `returnTo` unchanged.
 */
export function hfLoginUrl(returnTo: string, options: HfLoginOptions = {}): string {
  const endpoint = authUrl("/api/v1/auth/hf/login");
  const authority = new URL(endpoint, window.location.origin).origin;
  const target =
    authority === window.location.origin
      ? returnTo
      : new URL(returnTo, window.location.origin).toString();
  const params = new URLSearchParams({ return_to: target });
  if (options.authorizeInference) params.set("authorize_inference", "true");
  if (options.collectEmail) params.set("collect_email", "true");
  if (options.authorizeBucket) params.set("authorize_bucket", "true");
  if (options.bucketCreate) params.set("bucket_create", "true");
  return `${endpoint}?${params.toString()}`;
}

/**
 * Resolve the operational dashboard on the canonical auth authority.
 *
 * Staging deliberately does not run production CRON jobs or expose their
 * monitoring routes. Its release profile points VITE_AUTH_URL at production,
 * where the shared session is already valid.
 */
export function adminDashboardUrl(): string {
  return authUrl("/admin-dashboard");
}

/**
 * Normalise a backend-provided asset URL so it always points at the API
 * origin. Backend responses include thumbnail paths like
 * `/api/thumbnails/<file>?fit=...` that the browser would otherwise resolve
 * against the Space iframe origin (`<owner>-<name>.static.hf.space`), 404ing.
 *
 * Absolute URLs (`http://`, `https://`, `data:`, `blob:`) and protocol-relative
 * URLs are returned untouched so we don't rewrite paper-supplied external
 * images.
 */
export function assetUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  if (
    value.startsWith("http://") ||
    value.startsWith("https://") ||
    value.startsWith("data:") ||
    value.startsWith("blob:") ||
    value.startsWith("//")
  ) {
    return value;
  }
  if (value.startsWith("/")) {
    const origin = getApiOrigin();
    return origin ? `${origin}${value}` : value;
  }
  return value;
}

/**
 * `true` for builds that should hide auth-driven UI (HF sign-in, bookmark
 * toggles, cron dashboard). Used by the HF Space mirror, which cannot share
 * the backend's session cookie across origins.
 */
export function isAuthDisabled(): boolean {
  return enabledBuildFlag(import.meta.env.VITE_DISABLE_AUTH);
}

/**
 * `true` only for builds that explicitly opt into the research chat UI.
 * Production intentionally leaves this unset; staging sets it in
 * `.env.staging`. Keep this separate from `VITE_CHAT_LIVE`, which selects the
 * transport implementation and must not make the interface public by itself.
 */
export function isChatEnabled(): boolean {
  return enabledBuildFlag(import.meta.env.VITE_CHAT_ENABLED);
}

/**
 * Canonical chat page for builds that can't host chat themselves. The Hugging
 * Face Space mirror can't carry the HF session cookie that chat requires, so
 * its chat entry points open this page in a new tab instead.
 */
export const CANONICAL_CHAT_URL = "https://paperswithcode.co/chat";

/** `true` for the Space mirror: chat entry points hand off to the canonical site. */
export function isChatMirror(): boolean {
  return isAuthDisabled() && !isChatEnabled();
}

export function isNativePdfReaderEnabled(): boolean {
  return enabledBuildFlag(import.meta.env.VITE_NATIVE_PDF_READER_ENABLED);
}

export function isPaperReaderChatEnabled(): boolean {
  return isChatEnabled() && enabledBuildFlag(import.meta.env.VITE_PAPER_READER_CHAT_ENABLED);
}

export function isCodexAddEvalsEnabled(): boolean {
  return enabledBuildFlag(import.meta.env.VITE_CODEX_ADD_EVALS_ENABLED);
}

export function isCodexEnrichPaperEnabled(): boolean {
  return enabledBuildFlag(import.meta.env.VITE_CODEX_ENRICH_PAPER_ENABLED);
}

/** `true` for the staging bundle and its canonical deployed hostname. */
export function isStagingEnvironment(): boolean {
  if (import.meta.env.MODE === "staging") return true;
  return typeof window !== "undefined"
    && window.location.hostname === "staging.paperswithcode.co";
}

/**
 * `true` when the bundle should route under the URL fragment.
 * Hugging Face Static Spaces:
 *  - boot the iframe at `/index.html` (no route for that in BrowserRouter →
 *    SPA falls through to NotFound),
 *  - return 404 for any deep link like `/papers` (no SPA fallback).
 * Using `HashRouter` instead of `BrowserRouter` sidesteps both problems by
 * keeping every route under the URL fragment. Keep this as an explicit build
 * flag: a remote API origin is useful in more contexts than Spaces, and should
 * not change public URL shape on `paperswithcode.co`.
 */
export function shouldUseHashRouter(): boolean {
  return enabledBuildFlag(import.meta.env.VITE_USE_HASH_ROUTER);
}
