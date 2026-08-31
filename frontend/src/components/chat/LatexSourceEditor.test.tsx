import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LatexSourceEditor } from "./LatexSourceEditor";

describe("LatexSourceEditor", () => {
  it("marks the host and CodeMirror content as excluded from analytics capture", async () => {
    render(
      <LatexSourceEditor
        path="main.tex"
        value="\\documentclass{article}"
        readOnly={false}
        onChange={vi.fn()}
      />,
    );

    const host = screen.getByTestId("latex-source-editor");
    expect(host).toHaveClass("ph-no-capture");
    expect(host).toHaveAttribute("data-ph-no-capture", "true");
    expect(host).toHaveAttribute("data-ph-no-autocapture", "true");

    await waitFor(() => {
      const content = host.querySelector(".cm-content");
      expect(content).toHaveClass("ph-no-capture");
      expect(content).toHaveAttribute("data-ph-no-capture", "true");
      expect(content).toHaveAttribute("data-ph-no-autocapture", "true");
    });
  });
});
