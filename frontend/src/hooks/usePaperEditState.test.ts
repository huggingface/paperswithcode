import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { isPaperEditSection } from "@/lib/paperCuration";
import { usePaperEditState } from "./usePaperEditState";

describe("usePaperEditState", () => {
  it("keeps at most one editor active", () => {
    const { result } = renderHook(() => usePaperEditState());

    act(() => result.current.openEditor("tasks"));
    expect(result.current.activeEditor).toBe("tasks");

    act(() => result.current.openEditor("methods"));
    expect(result.current.activeEditor).toBe("methods");

    act(() => result.current.setEditorOpen("methods", false));
    expect(result.current.activeEditor).toBeNull();
  });

  it("does not let a stale close event dismiss the active editor", () => {
    const { result } = renderHook(() => usePaperEditState());

    act(() => result.current.openEditor("methods"));
    act(() => result.current.setEditorOpen("tasks", false));

    expect(result.current.activeEditor).toBe("methods");
  });
});

describe("isPaperEditSection", () => {
  it.each([
    "tasks",
    "methods",
    "evaluations",
    "repositories",
    "project_pages",
    "hf_artifacts",
    "organizations",
    "source_url",
    "x_threads",
  ])("accepts the stored API section %s as an editor ID", (storedSection) => {
    expect(isPaperEditSection(storedSection)).toBe(true);
  });

  it("ignores unknown stored sections", () => {
    expect(isPaperEditSection("unknown")).toBe(false);
    expect(isPaperEditSection("project-pages")).toBe(false);
  });
});
