import { normalizePaperRouteId } from "@/lib/utils";

export function parseHostList(raw: string | undefined): string[] {
  return (raw ?? "")
    .split(",")
    .map((host) => host.trim().toLowerCase())
    .filter(Boolean);
}

// Extra hostnames (such as the origin server IP) that stored links may use for
// this site; supplied at build time instead of being committed to source.
const INTERNAL_HOSTS = new Set([
  "paperswithcode.co",
  "www.paperswithcode.co",
  "localhost",
  "127.0.0.1",
  ...parseHostList(import.meta.env.VITE_INTERNAL_HOST_ALIASES),
]);

const INTERNAL_PATH_PREFIXES = [
  "/methods",
  "/paper",
  "/papers",
  "/tasks",
  "/benchmark",
  "/conferences",
];

export function resolveInternalPath(
  href: string | undefined,
  origin = window.location.origin,
): string | null {
  if (!href) return null;

  let path: string;
  if (href.startsWith("/")) {
    path = href;
  } else {
    try {
      const url = new URL(href, origin);
      if (!INTERNAL_HOSTS.has(url.hostname)) return null;
      path = `${url.pathname}${url.search}${url.hash}`;
    } catch {
      return null;
    }
  }

  const pathname = path.split(/[?#]/, 1)[0];
  return INTERNAL_PATH_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  )
    ? path
    : null;
}

export function extractPaperRouteId(internalPath: string): string | null {
  const pathname = internalPath.split(/[?#]/, 1)[0];
  const match = pathname.match(/^\/papers?\/([^/]+)$/);
  if (!match || match[1].includes("%")) return null;

  const routeId = match[1];
  const isModernArxiv = /^\d{4}[.-]\d{4,5}(?:v\d+)?$/.test(routeId);
  const isExternalPaperId = /^[1-9]\d*$/.test(routeId);
  if (!isModernArxiv && !isExternalPaperId) return null;

  return normalizePaperRouteId(routeId);
}
