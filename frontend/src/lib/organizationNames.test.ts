import { describe, expect, it } from "vitest";

import { organizationShortName } from "./organizationNames";

describe("organizationShortName", () => {
  it.each([
    ["University of Electronic Science and Technology of China", "uestc", "UESTC"],
    ["Beijing University of Posts and Telecommunications", "bupt", "BUPT"],
    ["Shenzhen Institutes of Advanced Technology, Chinese Academy of Sciences", "siat-cas", "SIAT-CAS"],
    ["Mohamed Bin Zayed University of Artificial Intelligence", "mbzuai", "MBZUAI"],
    ["Agency for Science, Technology and Research", "a-star", "A-STAR"],
  ])("abbreviates %s from its acronym slug", (name, slug, expected) => {
    expect(organizationShortName({ name, slug })).toBe(expected);
  });

  it.each([
    ["Tsinghua University", "tsinghua"],
    ["Deep Cognition and Language Research (DeCLaRe) Lab", "declare-lab"],
    ["AI Safety and Alignment Group at the ELLIS Institute Tübingen and MPI-IS", "aisa-group"],
    ["Hong Kong University of Science and Technology(GuangZhou)", "hkust-gz2"],
    ["Tom Goldstein's Lab at University of Maryland, College Park", "tomg-group-umd"],
  ])("keeps no short name for %s", (name, slug) => {
    expect(organizationShortName({ name, slug })).toBeNull();
  });
});
