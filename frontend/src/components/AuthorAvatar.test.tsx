import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuthorAvatar } from "@/components/AuthorAvatar";

describe("AuthorAvatar", () => {
  it("shows an uploaded Hugging Face avatar", () => {
    const { container } = render(
      <AuthorAvatar className="x" name="Zihao Yue" url="https://cdn-avatars.huggingface.co/a.jpeg" />,
    );
    expect(container.querySelector("img")).toHaveAttribute("src", "https://cdn-avatars.huggingface.co/a.jpeg");
  });

  it.each(["/avatars/default.svg", "https://huggingface.co/avatars/default.svg", null])(
    "falls back to initials for default avatar %s",
    (url) => {
      const { container } = render(<AuthorAvatar className="x" name="Zihao  Yue" url={url} />);
      expect(container.querySelector("img")).toBeNull();
      expect(container.textContent).toBe("ZY");
    },
  );

  it("falls back to initials when the image fails to load", () => {
    const { container } = render(
      <AuthorAvatar className="x" name="Ada Byron Lovelace" url="https://cdn-avatars.huggingface.co/gone.png" />,
    );
    fireEvent.error(container.querySelector("img")!);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toBe("AL");
  });
});
