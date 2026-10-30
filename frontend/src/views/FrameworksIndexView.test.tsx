import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { FrameworkCard } from "@/views/FrameworksIndexView";
import type { Framework } from "@/lib/api/catalog.types";

const framework = (paperCount: number): Framework => ({
  id: "1",
  slug: "lerobot",
  name: "LeRobot",
  description: "Robotics framework",
  platforms: ["cpu"],
  github_url: "https://github.com/huggingface/lerobot",
  repository: "huggingface/lerobot",
  docs_url: null,
  introducing_paper_arxiv_id: "2401.00001",
  paper_count: paperCount,
});

const Location = () => <div data-testid="location">{useLocation().pathname}{useLocation().search}</div>;

describe("FrameworkCard", () => {
  it("labels the introducing paper and links a singular implemented-paper feed", () => {
    render(<FrameworkCard framework={framework(1)} />, { wrapper: MemoryRouter });

    expect(screen.getByRole("link", { name: "Introducing paper" })).toHaveAttribute(
      "href",
      "/paper/2401.00001",
    );
    expect(screen.getByRole("link", { name: "Implements 1 paper" })).toHaveAttribute(
      "href",
      "/papers?framework=lerobot",
    );
  });

  it("pluralizes counts and renders zero as a disabled non-link", () => {
    const { rerender } = render(<FrameworkCard framework={framework(2)} />, {
      wrapper: MemoryRouter,
    });
    expect(screen.getByRole("link", { name: "Implements 2 papers" })).toBeInTheDocument();

    rerender(<FrameworkCard framework={framework(0)} />);
    expect(screen.queryByRole("link", { name: "Implements 0 papers" })).toBeNull();
    expect(screen.getByText("Implements 0 papers")).toHaveAttribute("aria-disabled", "true");
  });

  it("opens the framework feed when the card is clicked or activated by keyboard", () => {
    render(
      <MemoryRouter>
        <FrameworkCard framework={framework(2)} />
        <Location />
      </MemoryRouter>,
    );

    const card = screen.getByRole("link", { name: "View papers implemented by LeRobot" });
    fireEvent.click(card);
    expect(screen.getByTestId("location")).toHaveTextContent("/papers?framework=lerobot");

    fireEvent.keyDown(card, { key: "Enter" });
    expect(screen.getByTestId("location")).toHaveTextContent("/papers?framework=lerobot");
  });
});
