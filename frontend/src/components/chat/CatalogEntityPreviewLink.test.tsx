import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatMarkdown } from "@/components/chat/ChatMarkdown";
import { parseCatalogEntityHref } from "@/components/chat/CatalogEntityPreviewLink";

const catalog = vi.hoisted(() => ({
  getTask: vi.fn(),
  getMethod: vi.fn(),
  getDatasetBySlug: vi.fn(),
}));
vi.mock("@/lib/api/catalog", () => ({ catalogApi: catalog }));

function renderMarkdown(text: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ChatMarkdown text={text} papers={{}} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("catalog entity citations", () => {
  beforeEach(() => vi.clearAllMocks());

  it("parses only well-formed task, method, and benchmark slugs", () => {
    expect(parseCatalogEntityHref("benchmark:imagenet-1k")).toEqual({
      kind: "benchmark",
      slug: "imagenet-1k",
    });
    expect(parseCatalogEntityHref("task:image-classification")?.kind).toBe("task");
    expect(parseCatalogEntityHref("method:vit")?.kind).toBe("method");
    expect(parseCatalogEntityHref("task:../admin")).toBeNull();
    expect(parseCatalogEntityHref("dataset:imagenet")).toBeNull();
  });

  it("links each kind to its catalog page", () => {
    renderMarkdown(
      "[ImageNet](benchmark:imagenet-1k), [classification](task:image-classification), [ViT](method:vision-transformer)",
    );

    expect(screen.getByRole("link", { name: "ImageNet" })).toHaveAttribute(
      "href",
      "/benchmark/imagenet-1k",
    );
    expect(screen.getByRole("link", { name: "classification" })).toHaveAttribute(
      "href",
      "/tasks/image-classification",
    );
    expect(screen.getByRole("link", { name: "ViT" })).toHaveAttribute(
      "href",
      "/methods/vision-transformer",
    );
  });

  it("shows a benchmark preview card on hover", async () => {
    catalog.getDatasetBySlug.mockResolvedValue({
      id: "72",
      name: "Imagenet-1k (ILSVRC-2012)",
      slug: "imagenet-1k",
      description: "ImageNet-1k is a dataset used for **image classification**.",
      paper_count: 245,
      introduced_year: 2014,
    });
    renderMarkdown("See the [ImageNet-1k leaderboard](benchmark:imagenet-1k).");

    await userEvent.hover(screen.getByRole("link", { name: "ImageNet-1k leaderboard" }));

    expect(await screen.findByText("Imagenet-1k (ILSVRC-2012)")).toBeInTheDocument();
    expect(screen.getByText("Benchmark")).toBeInTheDocument();
    expect(
      screen.getByText("ImageNet-1k is a dataset used for image classification."),
    ).toBeInTheDocument();
    expect(screen.getByText("245 papers · Introduced 2014")).toBeInTheDocument();
    expect(catalog.getDatasetBySlug).toHaveBeenCalledWith("imagenet-1k");
  });

  it("shows a task preview with its image", async () => {
    catalog.getTask.mockResolvedValue({
      id: "1",
      name: "Image Classification",
      slug: "image-classification",
      level: 0,
      paper_count: 3098,
      image_url: "https://example.com/task.png",
    });
    renderMarkdown("[Image classification](task:image-classification)");

    await userEvent.hover(screen.getByRole("link", { name: "Image classification" }));

    expect(await screen.findByText("Image Classification")).toBeInTheDocument();
    expect(screen.getByTestId("catalog-preview-image")).toHaveAttribute(
      "src",
      "https://example.com/task.png",
    );
    expect(screen.getByText("3,098 papers")).toBeInTheDocument();
  });

  it("renders a malformed catalog slug as plain text", () => {
    const { container } = renderMarkdown("[Bad](task:../admin)");

    expect(screen.queryByRole("link", { name: "Bad" })).toBeNull();
    expect(container.querySelector(".chat-invalid-citation")?.textContent).toBe("Bad");
  });
});
