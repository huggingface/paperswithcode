
const LOG_API_REQUESTS = import.meta.env.DEV;

export class ApiError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly response: string;
  readonly detail: unknown;
  readonly code?: string;
  /** Dialog text; preserves raw non-JSON failures without changing Error.message. */
  readonly displayMessage: string;

  constructor(response: Response, body: string) {
    super(`API request failed: ${response.status} ${response.statusText}`);
    this.name = "ApiError";
    this.status = response.status;
    this.statusText = response.statusText;
    this.response = body;
    try {
      this.detail = JSON.parse(body)?.detail;
      if (typeof this.detail === "string") {
        this.message = this.detail;
      }
      if (Array.isArray(this.detail)) {
        const first: unknown = this.detail[0];
        if (
          typeof first === "object" && first !== null &&
          "msg" in first && typeof first.msg === "string"
        ) {
          this.message = first.msg;
        }
      }
      if (
        typeof this.detail === "object" &&
        this.detail !== null &&
        "code" in this.detail &&
        typeof this.detail.code === "string"
      ) {
        this.code = this.detail.code;
      }
      if (
        typeof this.detail === "object" &&
        this.detail !== null &&
        "message" in this.detail &&
        typeof this.detail.message === "string"
      ) {
        const help =
          "help" in this.detail && typeof this.detail.help === "string"
            ? ` See ${this.detail.help} for help.`
            : "";
        this.message = `${this.detail.message}${help}`;
      }
    } catch {
      this.detail = undefined;
      this.displayMessage = body || this.message;
      return;
    }
    this.displayMessage = this.message;
  }
}

/** User-facing failure text, with an operation-specific fallback for unknown errors. */
export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.displayMessage || fallback;
  if (
    typeof error === "object" && error !== null &&
    "message" in error && typeof error.message === "string"
  ) {
    return error.message || fallback;
  }
  return fallback;
}

export type ApiRequest = <T>(endpoint: string, options?: RequestInit) => Promise<T>;

export class ApiTransport {
  constructor(private readonly baseUrl: string) {}

  async fetch(endpoint: string, options?: RequestInit): Promise<Response> {
    const url = `${this.baseUrl}${endpoint}`;
    if (LOG_API_REQUESTS) console.log(`[API] Requesting: ${url}`);

    try {
      const { headers, ...requestOptions } = options ?? {};
      const method = (requestOptions.method ?? "GET").toUpperCase();
      const defaultCache: RequestCache = method === "GET" ? "default" : "no-store";
      const requestHeaders = new Headers(headers);
      if (typeof requestOptions.body === "string" && !requestHeaders.has("Content-Type")) {
        requestHeaders.set("Content-Type", "application/json");
      }
      const response = await fetch(url, {
        ...requestOptions,
        cache: requestOptions.cache ?? defaultCache,
        credentials: requestOptions.credentials ?? "include",
        headers: requestHeaders,
      });

      if (LOG_API_REQUESTS) {
        console.log(`[API] Response from ${url}:`, response.status, response.statusText);
      }
      return response;
    } catch (error) {
      console.error(`[API] Request to ${url} failed:`, error);
      throw error;
    }
  }

  /** Like `fetch`, but rejects non-2xx responses with an `ApiError`. */
  async fetchOk(endpoint: string, options?: RequestInit): Promise<Response> {
    const response = await this.fetch(endpoint, options);
    if (!response.ok) {
      const error = new ApiError(response, await response.text());
      console.error("[API] Error response:", error.response);
      throw error;
    }
    return response;
  }

  async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = await this.fetchOk(endpoint, options);
    if (response.status === 204) return undefined as T;

    const data = await response.json();
    if (LOG_API_REQUESTS) console.log("[API] Success:", data);
    return data;
  }
}
