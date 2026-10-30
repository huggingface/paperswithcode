import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, ApiTransport, getApiErrorMessage } from "./apiTransport";

describe("API transport", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("constructs the URL and parses a successful JSON response", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ results: ["paper"] }), { status: 200 }),
    );
    const transport = new ApiTransport("https://example.test/api/v1");

    await expect(transport.request<{ results: string[] }>("/papers"))
      .resolves.toEqual({ results: ["paper"] });

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("https://example.test/api/v1/papers");
    expect(options).toEqual(expect.objectContaining({
      cache: "default",
      credentials: "include",
    }));
    expect(new Headers(options?.headers).has("Content-Type")).toBe(false);
  });

  it("labels only string bodies as JSON so form uploads keep their boundary", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      async () => new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    const transport = new ApiTransport("https://example.test");

    await transport.request("/json", { method: "POST", body: JSON.stringify({ a: 1 }) });
    await transport.request("/upload", { method: "POST", body: new FormData() });
    await transport.request("/text", {
      method: "POST",
      body: "plain",
      headers: { "Content-Type": "text/plain" },
    });

    const contentType = (call: number) =>
      new Headers(fetchMock.mock.calls[call][1]?.headers).get("Content-Type");
    expect(contentType(0)).toBe("application/json");
    expect(contentType(1)).toBeNull();
    expect(contentType(2)).toBe("text/plain");
  });

  it("returns undefined for an empty 204 response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, { status: 204 }),
    );

    await expect(
      new ApiTransport("https://example.test").request<void>("/empty", {
        method: "DELETE",
      }),
    ).resolves.toBeUndefined();
  });

  it("exposes raw responses with the same credential and cache defaults", async () => {
    const response = new Response("stream", { status: 200 });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response);

    await expect(
      new ApiTransport("https://example.test/api/v1").fetch("/chat/stream", {
        headers: { Accept: "text/event-stream" },
      }),
    ).resolves.toBe(response);

    const options = fetchMock.mock.calls[0][1];
    expect(options).toEqual(expect.objectContaining({
      cache: "default",
      credentials: "include",
    }));
    expect(new Headers(options?.headers).get("Accept")).toBe("text/event-stream");
  });

  it("includes browser credentials and never sends an admin token", async () => {
    window.localStorage.setItem("cronAdminToken", "secret-admin-token");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );

    await new ApiTransport("https://example.test").request("/admin");

    const options = fetchMock.mock.calls[0][1];
    expect(options?.credentials).toBe("include");
    expect(new Headers(options?.headers).has("X-Admin-Token")).toBe(false);
    window.localStorage.removeItem("cronAdminToken");
  });

  it("returns a typed error without applying browser policy", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: "stale_catalog_version" } }), {
        status: 409,
        statusText: "Conflict",
      }),
    );
    const conflict = vi.fn();
    const stale = vi.fn();
    window.addEventListener("pwc:catalog-conflict", conflict);
    window.addEventListener("pwc:auth-stale", stale);

    const result = new ApiTransport("https://example.test").request("/unrelated", {
      method: "POST",
    });

    await expect(result).rejects.toEqual(
      expect.objectContaining<ApiError>({
        name: "ApiError",
        message: "API request failed: 409 Conflict",
        displayMessage: "API request failed: 409 Conflict",
        status: 409,
        statusText: "Conflict",
        response: JSON.stringify({ detail: { code: "stale_catalog_version" } }),
        detail: { code: "stale_catalog_version" },
        code: "stale_catalog_version",
      }),
    );
    expect(conflict).not.toHaveBeenCalled();
    expect(stale).not.toHaveBeenCalled();
    window.removeEventListener("pwc:catalog-conflict", conflict);
    window.removeEventListener("pwc:auth-stale", stale);
  });

  it("does not notify auth state for unauthorized responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not authenticated" }), {
        status: 401,
        statusText: "Unauthorized",
      }),
    );
    const stale = vi.fn();
    window.addEventListener("pwc:auth-stale", stale);

    await expect(
      new ApiTransport("https://example.test").request("/me", { method: "GET" }),
    ).rejects.toMatchObject({ status: 401 });

    expect(stale).not.toHaveBeenCalled();
    window.removeEventListener("pwc:auth-stale", stale);
  });

  it("surfaces structured rate-limit guidance", () => {
    const response = new Response(null, {
      status: 429,
      statusText: "Too Many Requests",
    });
    const error = new ApiError(
      response,
      JSON.stringify({
        detail: {
          code: "submission_rate_limited",
          message: "Submission limit reached.",
          help: "/rate-limits",
        },
      }),
    );

    expect(error.message).toBe(
      "Submission limit reached. See /rate-limits for help.",
    );
    expect(error.code).toBe("submission_rate_limited");
  });
});

describe("editing error messages", () => {
  it.each([
    ["No permission", "No permission"],
    [[{ loc: ["body", "url"], msg: "Invalid URL" }], "Invalid URL"],
    [{ code: "limited", message: "Try later", help: "/limits" }, "Try later See /limits for help."],
    [{ code: "limited", message: "Try later" }, "Try later"],
    [[], "API request failed: 422 Unprocessable Entity"],
    [[null], "API request failed: 422 Unprocessable Entity"],
    [[{ msg: 123 }], "API request failed: 422 Unprocessable Entity"],
    [{ unexpected: true }, "API request failed: 422 Unprocessable Entity"],
  ])("normalizes detail %j without losing the response contract", (detail, message) => {
    const body = JSON.stringify({ detail });
    const error = new ApiError(new Response(null, {
      status: 422, statusText: "Unprocessable Entity",
    }), body);
    expect(getApiErrorMessage(error, "Save failed")).toBe(message);
    expect(error).toMatchObject({ status: 422, statusText: "Unprocessable Entity", detail, response: body });
  });

  it.each(["upstream unavailable", "{invalid json", ""]) (
    "preserves the legacy status message and raw non-JSON text %j", (body) => {
      const error = new ApiError(new Response(null, { status: 502, statusText: "Bad Gateway" }), body);
      expect(error.message).toBe("API request failed: 502 Bad Gateway");
      expect(error.response).toBe(body);
      expect(error.detail).toBeUndefined();
      expect(getApiErrorMessage(error, "Save failed")).toBe(body || error.message);
    },
  );

  it.each([null, undefined, {}, new Error(""), "unexpected"]) (
    "uses the operation fallback for an unrecognized failure %j", (error) => {
      expect(getApiErrorMessage(error, "Save failed")).toBe("Save failed");
    },
  );

  it("preserves ordinary network errors without wrapping them", async () => {
    const error = new TypeError("Failed to fetch");
    vi.spyOn(globalThis, "fetch").mockRejectedValue(error);
    await expect(new ApiTransport("https://example.test").request("/papers")).rejects.toBe(error);
    expect(getApiErrorMessage(error, "Save failed")).toBe("Failed to fetch");
  });
});
