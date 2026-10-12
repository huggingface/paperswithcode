import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LatexText } from "@/components/LatexTitle";

describe("LatexText literal highlighting", () => {
  it("highlights query terms without interpreting hostile text or breaking LaTeX", async () => {
    const { container } = render(
      <LatexText
        text={'Needle <img src=x onerror="alert(1)"> with $x_i$'}
        highlight={'needle <img'}
      />,
    );
    expect(screen.getByText("Needle", { selector: "mark" })).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    await waitFor(() => expect(container.querySelector(".katex")).not.toBeNull());
  });
});
