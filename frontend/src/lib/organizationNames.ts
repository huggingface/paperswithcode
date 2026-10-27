/** Names longer than this crowd paper titles and the organization heading. */
export const LONG_ORGANIZATION_NAME_LENGTH = 32;

// Letters a reader would pick for an acronym: word initials and capitals.
const ACRONYM_LETTERS = /(?<![\p{L}\p{N}])[\p{L}\p{N}]|\p{Lu}/gu;

export function isLongOrganizationName(name: string): boolean {
  return name.length > LONG_ORGANIZATION_NAME_LENGTH;
}

/**
 * Short form of a long organization name, taken from its slug when the slug
 * is an acronym of the name ("uestc" → "UESTC" for "University of Electronic
 * Science and Technology of China"). Returns null for short names and for
 * slugs that are words rather than an acronym.
 */
export function organizationShortName(organization: {
  name: string;
  slug: string;
}): string | null {
  const { name, slug } = organization;
  if (!isLongOrganizationName(name) || slug.length > 10) return null;
  const letters = (name.match(ACRONYM_LETTERS) ?? []).join("").toLowerCase();
  let position = 0;
  for (const char of slug.replace(/-/g, "")) {
    position = letters.indexOf(char, position) + 1;
    if (position === 0) return null;
  }
  return slug.toUpperCase();
}
