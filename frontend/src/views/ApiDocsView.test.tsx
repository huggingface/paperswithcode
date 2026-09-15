import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import ApiDocsView from "./ApiDocsView";
import {
  codeExample,
  exampleUrl,
  publicSpecQuery,
  type PublicSpec,
} from "@/lib/api/publicDocs";

const spec: PublicSpec = {
  paths: {
    "/api/v1/papers/search": {
      get: {
        operationId: "search",
        summary: "Search papers",
        parameters: [
          {
            name: "mode",
            in: "query",
            required: true,
            schema: { type: "string", enum: ["keyword"] },
          },
        ],
        "x-example-parameters": { q: "attention & memory", mode: "keyword" },
        responses: {
          "200": {
            description: "Success",
            content: {
              "application/json": {
                schema: { $ref: "#/components/schemas/Results" },
              },
            },
          },
        },
      },
    },
  },
  components: {
    schemas: {
      Results: {
        type: "object",
        properties: {
          count: { type: "integer", description: "Matching papers" },
        },
      },
    },
  },
};
function show(data = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  if (data) client.setQueryData(publicSpecQuery.queryKey, spec);
  return render(
    <QueryClientProvider client={client}>
      <ApiDocsView />
    </QueryClientProvider>,
  );
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
describe("public API documentation", () => {
  it("renders schema fields, limits, beta policy, and generated examples", () => {
    show();
    expect(
      screen.getByRole("heading", { name: "Papers With Code API" }),
    ).toBeTruthy();
    expect(screen.getByText("Matching papers")).toBeTruthy();
    expect(screen.getByText(/14 days/)).toBeTruthy();
    expect(screen.getByText(/120 requests\/minute/)).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Results" }).getAttribute("href"),
    ).toBe("#model-Results");
    fireEvent.click(screen.getByRole("button", { name: "Python" }));
    expect(screen.getByText(/response.raise_for_status/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "JavaScript" }));
    expect(screen.getByText(/credentials: "omit"/)).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: /execute|send request/i }),
    ).toBeNull();
  });
  it("shows an actionable error when schema delivery fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    show(false);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
  it("encodes parameters and produces runnable code without credentials", () => {
    const url = exampleUrl(
      "/api/v1/papers/search",
      spec.paths["/api/v1/papers/search"].get,
    );
    expect(new URL(url).searchParams.get("q")).toBe("attention & memory");
    expect(new URL(url).searchParams.get("mode")).toBe("keyword");
    expect(codeExample(url, "curl")).toContain("--fail-with-body");
  });
});
