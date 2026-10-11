import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { PdfToolbar } from "./PdfToolbar";

describe("PdfToolbar", () => {
  it("supports page, zoom, and search controls", () => {
    const onPage = vi.fn();
    const onZoom = vi.fn();
    const onToggleSearch = vi.fn();
    const onCloseSearch = vi.fn();
    const header = document.createElement("header");
    header.className = "app-header";
    const logo = document.createElement("span");
    logo.className = "brand-mark";
    logo.getBoundingClientRect = () => ({ left: 48 } as DOMRect);
    header.append(logo);
    document.body.append(header);
    const view = render(<MemoryRouter><PdfToolbar
        paperTitle="Example Paper"
        paperHref="/paper/2501.00001"
        resources={{
          repository: { href: "https://github.com/example/paper", stars: 1234 },
          projectPage: { href: "https://example.org/project", label: "example.org" },
          huggingFace: { href: "https://huggingface.co/papers/2501.00001", count: 3 },
        }}
        page={3}
        pages={12}
        zoomPercent={125}
        searchOpen
        searchQuery=""
        searchMatch={0}
        searchCount={0}
        searching={false}
        onPage={onPage}
        onZoom={onZoom}
        onZoomIn={vi.fn()}
        onZoomOut={vi.fn()}
        onToggleSearch={onToggleSearch}
        onCloseSearch={onCloseSearch}
        onSearchQuery={vi.fn()}
        onSearch={vi.fn()}
      /></MemoryRouter>);

    expect(view.container.querySelector(".pdf-toolbar")).toHaveStyle({
      "--reader-title-inset": "48px",
    });
    expect(screen.getByRole("link", { name: "Example Paper — open paper page" }))
      .toHaveAttribute("href", "/paper/2501.00001");
    const backLink = screen.getByRole("link", { name: "Back" });
    const titleLink = screen.getByRole("link", { name: "Example Paper — open paper page" });
    expect(backLink).toHaveAttribute("href", "/paper/2501.00001");
    expect(backLink.compareDocumentPosition(titleLink) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open official GitHub repository" }))
      .toHaveAttribute("href", "https://github.com/example/paper");
    expect(screen.queryByText("example/paper")).not.toBeInTheDocument();
    expect(screen.getByLabelText("1234 GitHub stars")).toHaveTextContent("★ 1,234");
    expect(screen.getByRole("link", { name: "Open project page at example.org" }))
      .toHaveAttribute("href", "https://example.org/project");
    expect(screen.getByRole("link", { name: "Open 3 Hugging Face artifacts" }))
      .toHaveAttribute("href", "https://huggingface.co/papers/2501.00001");
    expect(screen.getByRole("spinbutton", { name: "Page 3 of 12" })).toHaveAttribute("type", "number");
    expect(screen.queryByText(/arXiv:/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(onPage).toHaveBeenCalledWith(2);
    const zoomInput = screen.getByRole("textbox", { name: "Zoom 125%" });
    fireEvent.change(zoomInput, { target: { value: "137" } });
    fireEvent.submit(zoomInput);
    expect(onZoom).toHaveBeenLastCalledWith(1.37);
    fireEvent.change(zoomInput, { target: { value: "900%" } });
    fireEvent.submit(zoomInput);
    expect(onZoom).toHaveBeenLastCalledWith(4);
    expect(zoomInput).toHaveValue("400%");
    expect(screen.queryByRole("button", { name: "Fit width" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(onToggleSearch).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Close search" }));
    expect(onCloseSearch).toHaveBeenCalledOnce();
    expect(screen.queryByRole("link", { name: "Open original" })).not.toBeInTheDocument();
    header.remove();
  });
});
