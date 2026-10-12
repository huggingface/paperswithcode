import { describe, expect, it } from "vitest";
import { groupBenchmarkVariants, variantLabel } from "./benchmarkVariants";

type Row = { id: string; name: string; parent?: string };
const parentOf = (row: Row) => row.parent;

describe("groupBenchmarkVariants", () => {
  it("collapses listed variants under their parent at the first member's position", () => {
    const rows: Row[] = [
      { id: "1", name: "KITTI (metric)" },
      { id: "3", name: "KITTI (relative, depth-aligned)", parent: "2" },
      { id: "2", name: "KITTI (relative)" },
      { id: "4", name: "DIODE (relative, MoGe protocol)", parent: "9" },
      { id: "5", name: "KITTI (relative, log-aligned)", parent: "2" },
    ];
    const groups = groupBenchmarkVariants(rows, parentOf);
    expect(groups.map((g) => g.members.map((m) => m.id))).toEqual([
      ["1"],
      ["2", "3", "5"],
      ["4"],
    ]);
  });

  it("follows nested variants to the listed root and tolerates cycles", () => {
    const rows: Row[] = [
      { id: "a", name: "A" },
      { id: "b", name: "A (x)", parent: "a" },
      { id: "c", name: "A (x, y)", parent: "b" },
      { id: "d", name: "D", parent: "e" },
      { id: "e", name: "E", parent: "d" },
    ];
    const groups = groupBenchmarkVariants(rows, parentOf);
    expect(groups[0].members.map((m) => m.id)).toEqual(["a", "b", "c"]);
    expect(groups.slice(1).flatMap((g) => g.members.map((m) => m.id)).sort()).toEqual(["d", "e"]);
  });
});

describe("variantLabel", () => {
  it("labels a variant by the qualifiers it adds to its parent", () => {
    expect(variantLabel("KITTI (relative, depth-aligned)", "KITTI (relative)")).toBe("depth-aligned");
    expect(variantLabel("DIODE (relative, MoGe protocol)", "DIODE (relative)")).toBe("MoGe protocol");
    expect(variantLabel("ScanNet (relative, log-aligned)", "ScanNet")).toBe("relative, log-aligned");
    expect(variantLabel("KITTI (relative)")).toBe("standard");
  });
});
