import { afterEach, describe, expect, it, vi } from "vitest";

import { adminDashboardUrl, hfLoginUrl } from "./apiUrl";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("adminDashboardUrl", () => {
  it("uses the current origin when there is no separate auth authority", () => {
    vi.stubEnv("VITE_AUTH_URL", "");

    expect(adminDashboardUrl()).toBe("/admin-dashboard");
  });

  it("uses the production auth authority in a staging build", () => {
    vi.stubEnv("VITE_AUTH_URL", "https://paperswithcode.co/");

    expect(adminDashboardUrl()).toBe(
      "https://paperswithcode.co/admin-dashboard",
    );
  });
});

describe("hfLoginUrl", () => {
  const login = (...args: Parameters<typeof hfLoginUrl>) =>
    new URL(hfLoginUrl(...args), window.location.origin);

  it("keeps ordinary sign-in limited to account identity", () => {
    const url = login("/settings");

    expect(url.pathname).toBe("/api/v1/auth/hf/login");
    expect([...url.searchParams.keys()]).toEqual(["return_to"]);
    expect(url.searchParams.get("return_to")).toBe("/settings");
  });

  it("adds only the permissions a caller requests", () => {
    expect(login("/chat", { authorizeInference: true }).searchParams.get("authorize_inference")).toBe("true");
    expect(login("/request-access", { collectEmail: true }).searchParams.get("collect_email")).toBe("true");
    const bucket = login("/paper/1", { authorizeBucket: true, bucketCreate: false });
    expect(bucket.searchParams.get("authorize_bucket")).toBe("true");
    expect(bucket.searchParams.has("bucket_create")).toBe(false);
  });

  it("sends an absolute return URL to a separate auth authority", () => {
    vi.stubEnv("VITE_AUTH_URL", "https://paperswithcode.co");

    const url = new URL(hfLoginUrl("/saved?x=1"));

    expect(url.origin).toBe("https://paperswithcode.co");
    expect(url.searchParams.get("return_to")).toBe(`${window.location.origin}/saved?x=1`);
  });
});
