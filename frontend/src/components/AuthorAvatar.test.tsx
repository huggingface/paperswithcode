import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuthorAvatar } from "@/components/AuthorAvatar";

describe("AuthorAvatar", () => {
  it("shows an uploaded Hugging Face avatar", () => {
    const { container } = render(
      <AuthorAvatar className="x" url="https://cdn-avatars.huggingface.co/a.jpeg" />,
    );
    expect(container.querySelector("img")).toHaveAttribute("src", "https://cdn-avatars.huggingface.co/a.jpeg");
  });

  it.each(["/avatars/default.svg", "https://huggingface.co/avatars/default.svg", null])(
    "renders nothing for default avatar %s",
    (url) => {
      const { container } = render(<AuthorAvatar className="x" url={url} />);
      expect(container).toBeEmptyDOMElement();
    },
  );

  it("removes an avatar that fails to load", () => {
    const { container } = render(
      <AuthorAvatar className="x" url="https://cdn-avatars.huggingface.co/gone.png" href="https://huggingface.co/u" />,
    );
    fireEvent.error(container.querySelector("img")!);
    expect(container).toBeEmptyDOMElement();
  });
});
