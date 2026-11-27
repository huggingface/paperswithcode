import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { RunnerBadge, RunnerSummary } from "./CodexJobQueue";

it("labels live Pi, Pi shadow, and Codex jobs", () => {
  render(
    <>
      <RunnerBadge job={{ runner: "pi", trigger: "hf-daily-cron" }} />
      <RunnerBadge job={{ runner: "pi", trigger: "pi-shadow" }} />
      <RunnerBadge job={{ runner: undefined, trigger: "admin" }} />
    </>,
  );

  expect(screen.getByText("Pi")).toBeInTheDocument();
  expect(screen.getByText("Pi shadow")).toHaveAttribute("title", expect.stringContaining("never applied"));
  expect(screen.getByText("Codex")).toBeInTheDocument();
});

it("summarizes which runner curates and how each fared", () => {
  render(
    <RunnerSummary
      summary={{
        enrich_runner: "pi",
        codex_model: "gpt-6-luna",
        pi_model: "deepseek-ai/DeepSeek-V4.1-Flash-1017",
        daily_last_7_days: [
          { runner: "codex", kind: "add-evals", completed: 40, failed: 1 },
          { runner: "pi", kind: "enrich-paper", completed: 38, failed: 2 },
        ],
        shadow: { sample_rate: 0.2, completed_last_7_days: 9, failed_last_7_days: 0, pairs_unjudged: 7 },
      }}
    />,
  );

  expect(screen.getByText(/Daily enrich runs on Pi \(deepseek-ai\/DeepSeek-V4.1-Flash-1017\)/)).toBeInTheDocument();
  expect(screen.getByText(/Pi Enrich paper 38 completed, 2 failed/)).toBeInTheDocument();
  expect(screen.getByText(/Pi shadow \(20% of daily papers\)/)).toHaveTextContent("7 pairs await");
});
