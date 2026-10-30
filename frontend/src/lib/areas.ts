// General leads as the broad catchall, the modality areas follow in a curated
// order and "Other" closes; areas outside this map sort alphabetically after
// it, so newly added areas show up without code edits.
const AREA_ORDER: Record<string, number> = {
  general: 0,
  vision: 1,
  video: 2,
  language: 3,
  audio: 4,
  other: 5,
};

const areaRank = (name: string) =>
  AREA_ORDER[name.trim().toLowerCase().replace(/[\s_]+/g, "-")] ?? 999;

export const sortAreas = <T extends { name: string }>(areas: readonly T[]): T[] =>
  [...areas].sort((a, b) => areaRank(a.name) - areaRank(b.name) || a.name.localeCompare(b.name));
