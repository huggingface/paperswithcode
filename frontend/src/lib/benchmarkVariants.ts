// Groups protocol variants (e.g. "KITTI (relative, depth-aligned)") under
// their parent benchmark so the task page shows one row per dataset with the
// protocol versions as tabs, instead of one row per variant.

export interface BenchmarkVariantGroup<T> {
  key: string;
  members: T[];
}

const qualifiers = (name: string): string[] => {
  const match = name.match(/\(([^()]*)\)\s*$/);
  return match ? match[1].split(",").map((part) => part.trim()).filter(Boolean) : [];
};

/** Short tab label: the qualifiers a variant adds to its parent's name. */
export function variantLabel(name: string, parentName?: string): string {
  const own = qualifiers(name);
  if (parentName === undefined) return "standard";
  const inherited = new Set(qualifiers(parentName).map((q) => q.toLowerCase()));
  const added = own.filter((q) => !inherited.has(q.toLowerCase()));
  return added.length ? added.join(", ") : name;
}

/**
 * Collapse rows whose parent benchmark is also listed into the parent's
 * group. Groups keep the position of their first listed member; the parent
 * comes first within its group, followed by variants in list order.
 */
export function groupBenchmarkVariants<T extends { id: string }>(
  rows: T[],
  parentIdOf: (row: T) => string | null | undefined,
): BenchmarkVariantGroup<T>[] {
  const listed = new Map(rows.map((row) => [row.id, row]));
  const rootOf = (row: T): string => {
    const seen = new Set<string>([row.id]);
    let current = row;
    for (;;) {
      const parentId = parentIdOf(current);
      const parent = parentId ? listed.get(parentId) : undefined;
      if (!parent) return current.id;
      if (seen.has(parent.id)) return row.id;
      seen.add(parent.id);
      current = parent;
    }
  };

  const groups = new Map<string, T[]>();
  rows.forEach((row) => {
    const key = rootOf(row);
    groups.set(key, [...(groups.get(key) || []), row]);
  });
  return [...groups].map(([key, members]) => ({
    key,
    members: [
      listed.get(key)!,
      ...members.filter((member) => member.id !== key),
    ],
  }));
}
