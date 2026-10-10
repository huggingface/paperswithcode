import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useScrollToTop } from "@/hooks/useScrollToTop";

const ScrollHarness = () => {
  const navigate = useNavigate();
  useScrollToTop();

  return (
    <>
      <button onClick={() => navigate("?has_code=true")}>
        Change filter
      </button>
      <button onClick={() => navigate("/tasks/image-classification")}>
        Change page
      </button>
      <button onClick={() => navigate("/paper/2206.07990#results")}>
        Open paper results
      </button>
      <button onClick={() => navigate("/paper/2206.07990")}>
        Open paper top
      </button>
    </>
  );
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useScrollToTop", () => {
  it("preserves scroll for query changes and resets it for pathname changes", async () => {
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/tasks/ocr"]}>
        <ScrollHarness />
      </MemoryRouter>,
    );

    expect(scrollTo).toHaveBeenCalledWith({ top: 0, left: 0, behavior: "instant" });
    scrollTo.mockClear();

    await user.click(screen.getByRole("button", { name: "Change filter" }));
    expect(scrollTo).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Change page" }));
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, left: 0, behavior: "instant" });
  });

  it("leaves paper deep links to the section scroller and resets when the hash is removed", async () => {
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/paper/2206.07990#abstract"]}>
        <ScrollHarness />
      </MemoryRouter>,
    );

    expect(scrollTo).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Open paper results" }));
    expect(scrollTo).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Open paper top" }));
    expect(scrollTo).toHaveBeenCalledTimes(1);
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, left: 0, behavior: "instant" });
  });
});
