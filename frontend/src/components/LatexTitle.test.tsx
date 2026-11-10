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

describe("LatexText dollar amounts", () => {
  it("keeps prices literal while rendering inline math", async () => {
    const { container } = render(
      <LatexText
        text={
          "Costs $8 per million input tokens and $40 per million output tokens, "
          + "or $5, while $O(n^2)$ uses $\\alpha$ and $3 \\times 3$ kernels."
        }
      />,
    );
    await waitFor(() => expect(container.querySelectorAll(".katex")).toHaveLength(3));
    expect(container.textContent).toContain(
      "Costs $8 per million input tokens and $40 per million output tokens, or $5, while ",
    );
    const math = Array.from(container.querySelectorAll("annotation")).map((node) => node.textContent);
    expect(math).toEqual(["O(n^2)", "\\alpha", "3 \\times 3"]);
  });
});
