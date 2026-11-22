import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PendingPaperEdit } from "@/lib/pendingEdits";

const staging = vi.hoisted(() => ({ value: false }));
vi.mock("@/lib/apiUrl", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/apiUrl")>()),
  isStagingEnvironment: () => staging.value,
}));

import { reportSubmission, STAGING_SUBMISSION_TOAST } from "./submissionOutcome";

function report(status: string) {
  const toast = vi.fn();
  reportSubmission({ status } as PendingPaperEdit, {
    toast,
    queryClient: new QueryClient(),
    paperIds: ["42"],
    queuedDescription: "Thanks! An admin will review your proposed repositories shortly.",
  });
  return toast;
}

describe("reportSubmission", () => {
  afterEach(() => {
    staging.value = false;
  });

  it("promises admin review for a queued production edit", () => {
    expect(report("pending")).toHaveBeenCalledWith({
      title: "Edit submitted for review",
      description: "Thanks! An admin will review your proposed repositories shortly.",
    });
  });

  it("says a queued staging edit stays on staging", () => {
    staging.value = true;
    expect(report("pending")).toHaveBeenCalledWith(STAGING_SUBMISSION_TOAST);
  });

  it("reports an applied edit as live", () => {
    expect(report("approved")).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Edit applied" }),
    );
  });
});
