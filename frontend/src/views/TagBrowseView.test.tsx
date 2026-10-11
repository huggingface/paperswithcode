import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import {
  HealthcareMedicalAiHub,
  RecommendedFrameworkLinks,
  TaskBreadcrumb,
} from "@/views/TagBrowseView";

describe("HealthcareMedicalAiHub", () => {
  it("makes the four medical AI destinations directly discoverable", () => {
    render(
      <MemoryRouter>
        <HealthcareMedicalAiHub
          task={{
            id: "416",
            name: "Healthcare",
            slug: "healthcare",
            level: 0,
            paper_count: 3883,
          }}
          relatedTasks={[
            {
              id: "322",
              name: "Medical Imaging",
              slug: "medical-imaging",
              level: 0,
              paper_count: 1972,
            },
            {
              id: "714",
              name: "Medical Visual Question Answering",
              slug: "medical-visual-question-answering",
              level: 1,
              paper_count: 104,
            },
            {
              id: "715",
              name: "Medical Question Answering",
              slug: "medical-question-answering",
              level: 1,
              paper_count: 249,
            },
          ]}
        />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: "Explore Healthcare & Medical AI" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Clinical AI & Healthcare/ })).toHaveAttribute(
      "href",
      "#benchmarks",
    );
    expect(screen.getByRole("link", { name: /Medical Question Answering/ })).toHaveAttribute(
      "href",
      "/tasks/medical-question-answering",
    );
    expect(screen.getByRole("link", { name: /Medical Imaging/ })).toHaveAttribute(
      "href",
      "/tasks/medical-imaging",
    );
    expect(
      screen.getByRole("link", { name: /Medical Visual Question Answering/ }),
    ).toHaveAttribute("href", "/tasks/medical-visual-question-answering");
  });
});

describe("RecommendedFrameworkLinks", () => {
  it("links recommendations to their internal framework paper feeds", () => {
    render(
      <MemoryRouter>
        <RecommendedFrameworkLinks
          frameworks={[{
            id: "10",
            framework_id: "30",
            framework_slug: "transformers",
            framework_name: "Transformers",
            url: "https://github.com/huggingface/transformers",
            owner: "huggingface",
            name: "transformers",
            num_stars: 150_000,
          }]}
        />
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: /Transformers/ });
    expect(link).toHaveAttribute("href", "/papers?framework=transformers");
    expect(link).not.toHaveAttribute("target");
  });
});

describe("TaskBreadcrumb", () => {
  it("shows the task area and parent hierarchy without a Papers root", () => {
    render(
      <MemoryRouter>
        <TaskBreadcrumb
          area={{ id: "6", name: "Audio" }}
          parents={[
            {
              id: "11",
              name: "Speaker Recognition",
              slug: "speaker-recognition",
              level: 0,
            },
          ]}
          task={{
            id: "12",
            name: "Speaker Verification",
            slug: "speaker-verification",
            level: 1,
          }}
        />
      </MemoryRouter>,
    );

    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(breadcrumb).toHaveTextContent(
      "Tasks/Audio/Speaker Recognition/Speaker Verification",
    );
    expect(screen.getByRole("link", { name: "Tasks" })).toHaveAttribute(
      "href",
      "/tasks",
    );
    expect(screen.getByRole("link", { name: "Audio" })).toHaveAttribute(
      "href",
      "/tasks#area-audio",
    );
    expect(screen.queryByRole("link", { name: "Papers" })).toBeNull();
  });

  it("preserves 2D and 3D capitalization in task names", () => {
    const { rerender } = render(
      <MemoryRouter>
        <TaskBreadcrumb
          parents={[]}
          task={{
            id: "450",
            name: "3D Tracking",
            slug: "3D-tracking",
            level: 0,
          }}
        />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("navigation", { name: "Breadcrumb" }),
    ).toHaveTextContent("Tasks/3D Tracking");

    rerender(
      <MemoryRouter>
        <TaskBreadcrumb
          parents={[]}
          task={{
            id: "451",
            name: "2D Point Tracking",
            slug: "point-tracking",
            level: 0,
          }}
        />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("navigation", { name: "Breadcrumb" }),
    ).toHaveTextContent("Tasks/2D Point Tracking");
  });

  it("preserves AI capitalization in canonical task names", () => {
    render(
      <MemoryRouter>
        <TaskBreadcrumb
          parents={[]}
          task={{
            id: "416",
            name: "Healthcare & Medical AI",
            slug: "healthcare",
            level: 0,
          }}
        />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("navigation", { name: "Breadcrumb" }),
    ).toHaveTextContent("Tasks/Healthcare & Medical AI");
  });
});
