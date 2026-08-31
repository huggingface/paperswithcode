import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PaperDateFilter } from "@/components/PaperDateFilter";

describe("PaperDateFilter", () => {
  it("applies an inclusive range from the two-month calendar", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();

    render(<PaperDateFilter currentDate="2026-08-21" onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Select a range" }));

    const dialog = screen.getByRole("dialog", { name: "Select a date range" });
    expect(dialog).not.toHaveAttribute("aria-modal", "true");
    expect(within(dialog).getByText("August 2026")).toBeInTheDocument();
    expect(within(dialog).getByText("September 2026")).toBeInTheDocument();
    expect(within(dialog).getByRole("spinbutton", { name: "Start year" })).toHaveValue(2026);
    expect(within(dialog).getByRole("spinbutton", { name: "End year" })).toHaveValue(2026);
    expect(within(dialog).getByRole("button", { name: "2026-08-22" })).toBeDisabled();

    await user.click(within(dialog).getByRole("button", { name: "2026-08-03" }));
    await user.click(within(dialog).getByRole("button", { name: "2026-08-10" }));
    await user.click(within(dialog).getByRole("button", { name: "Apply" }));

    expect(onChange).toHaveBeenCalledWith({
      startDate: "2026-08-03",
      endDate: "2026-08-10",
    });
  });

  it("jumps each calendar to its entered year", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();

    render(<PaperDateFilter currentDate="2026-08-21" onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Select a range" }));
    const dialog = screen.getByRole("dialog", { name: "Select a date range" });
    const startYear = within(dialog).getByRole("spinbutton", { name: "Start year" });
    const endYear = within(dialog).getByRole("spinbutton", { name: "End year" });

    await user.clear(startYear);
    await user.type(startYear, "2023");
    await user.clear(endYear);
    await user.type(endYear, "2024");

    expect(within(dialog).getByText("August 2023")).toBeInTheDocument();
    expect(within(dialog).getByText("September 2024")).toBeInTheDocument();
  });

  it("navigates the start and end calendars independently", async () => {
    const user = userEvent.setup();

    render(<PaperDateFilter currentDate="2023-01-15" onChange={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Select a range" }));
    const dialog = screen.getByRole("dialog", { name: "Select a date range" });

    await user.click(within(dialog).getByRole("button", { name: "Previous start month" }));

    expect(within(dialog).getByText("December 2022")).toBeInTheDocument();
    expect(within(dialog).getByText("February 2023")).toBeInTheDocument();
    expect(within(dialog).getByRole("spinbutton", { name: "Start year" })).toHaveValue(2022);
    expect(within(dialog).getByRole("spinbutton", { name: "End year" })).toHaveValue(2023);

    await user.click(within(dialog).getByRole("button", { name: "Next start month" }));

    expect(within(dialog).getByText("January 2023")).toBeInTheDocument();
    expect(within(dialog).getByText("February 2023")).toBeInTheDocument();
    expect(within(dialog).getByRole("spinbutton", { name: "Start year" })).toHaveValue(2023);

    await user.click(within(dialog).getByRole("button", { name: "Next end month" }));

    expect(within(dialog).getByText("January 2023")).toBeInTheDocument();
    expect(within(dialog).getByText("March 2023")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Previous end month" }));

    expect(within(dialog).getByText("January 2023")).toBeInTheDocument();
    expect(within(dialog).getByText("February 2023")).toBeInTheDocument();
  });

  it("supports same-day ranges and resets the start for an earlier second click", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();

    render(<PaperDateFilter currentDate="2026-08-21" onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Select a range" }));
    const dialog = screen.getByRole("dialog", { name: "Select a date range" });

    await user.click(within(dialog).getByRole("button", { name: "2026-08-10" }));
    await user.click(within(dialog).getByRole("button", { name: "2026-08-03" }));
    expect(within(dialog).getByRole("button", { name: "Apply" })).toBeDisabled();

    await user.click(within(dialog).getByRole("button", { name: "2026-08-03" }));
    await user.click(within(dialog).getByRole("button", { name: "Apply" }));

    expect(onChange).toHaveBeenCalledWith({
      startDate: "2026-08-03",
      endDate: "2026-08-03",
    });
  });

  it("maps presets to explicit UTC dates and clears a custom range", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();

    render(
      <PaperDateFilter
        startDate="2026-08-03"
        endDate="2026-08-10"
        currentDate="2026-08-21"
        onChange={onChange}
      />,
    );

    expect(screen.getByRole("button", { name: "Change date range" })).toHaveTextContent(
      "Aug 3–10, 2026",
    );
    await user.click(screen.getByRole("button", { name: "Last Week" }));
    expect(onChange).toHaveBeenLastCalledWith({
      startDate: "2026-08-15",
      endDate: "2026-08-21",
    });

    await user.click(screen.getByRole("button", { name: "Last Month" }));
    expect(onChange).toHaveBeenLastCalledWith({
      startDate: "2026-07-23",
      endDate: "2026-08-21",
    });

    await user.click(screen.getByRole("button", { name: "Change date range" }));
    await user.click(screen.getByRole("button", { name: "Clear range" }));
    expect(onChange).toHaveBeenLastCalledWith({});
  });
});
