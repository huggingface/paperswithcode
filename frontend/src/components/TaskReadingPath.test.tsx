import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import TaskReadingPath from "@/components/TaskReadingPath";
import { catalogApi } from "@/lib/api/catalog";
import type { Paper } from "@/lib/api/papers.types";
import type { TaskReadingPath as TaskReadingPathData } from "@/lib/api/catalog.types";

function paper(id: string, title: string, arxivId: string | null, published: string): Paper {
  return { id, title, arxiv_id: arxivId, published } as Paper;
}

function renderPath() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TaskReadingPath taskId="object-detection" label="00/" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("TaskReadingPath", () => {
  it("lists steps in order with paper links and the curated label", async () => {
    const data: TaskReadingPathData = {
      task_id: "2",
      task_slug: "object-detection",
      source: "curated",
      steps: [
        {
          kind: "overview",
          title: "Get an overview",
          description: "A survey.",
          source: "curated",
          papers: [{ paper: paper("2090", "Object Detection in 20 Years", "1905.05055", "2019-05-13"), note: "Start here." }],
        },
        {
          kind: "recent",
          title: "Explore recent work",
          description: "Now.",
          source: "automatic",
          papers: [{ paper: paper("9", "External Detector", null, "2025-01-01"), note: null }],
        },
      ],
    };
    const spy = vi.spyOn(catalogApi, "taskReadingPath").mockResolvedValue(data);

    renderPath();

    expect(await screen.findByText("Start here")).toBeInTheDocument();
    expect(spy).toHaveBeenCalledWith("object-detection");
    expect(screen.getByText("curated")).toBeInTheDocument();
    expect(screen.getByText("1. Get an overview")).toBeInTheDocument();
    expect(screen.getByText("2. Explore recent work")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Object Detection in 20 Years/ })).toHaveAttribute(
      "href",
      "/paper/1905.05055",
    );
    expect(screen.getByRole("link", { name: /External Detector/ })).toHaveAttribute(
      "href",
      "/paper/9",
    );
  });

  it("renders nothing when the task has no path", async () => {
    const spy = vi.spyOn(catalogApi, "taskReadingPath").mockResolvedValue({
      task_id: "3",
      task_slug: "empty",
      source: "automatic",
      steps: [],
    });

    const { container } = renderPath();

    await vi.waitFor(() => expect(spy).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
