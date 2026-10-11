import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AstraRoboticsFeature } from "@/components/AstraRoboticsFeature";

describe("AstraRoboticsFeature", () => {
  it("links to the GPT-6 Astra collection", () => {
    render(
      <MemoryRouter>
        <AstraRoboticsFeature />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("link", { name: "Featured collection: GPT-6 Astra for Robotics" }),
    ).toHaveAttribute("href", "/astra-for-robotics");
  });
});
