/** One run of page text; runs with different `item` values are separate PDF text items. */
export interface PdfTextRun {
  text: string;
  item: number;
}

export interface PdfAuthor {
  id: string;
  name: string;
}

export interface PdfTextPosition {
  run: number;
  offset: number;
}

export interface PdfAuthorMatch {
  authorId: string;
  start: PdfTextPosition;
  /** Exclusive. */
  end: PdfTextPosition;
}

// What separates two letters of the page text, weakest first. A joiner (hyphen,
// apostrophe, detached accent) sits inside a word; a space ends one; anything
// else (commas, digits, affiliation marks, `@`) ends a name outright.
const NONE = 0;
const JOINER = 1;
const SPACE = 2;
const HARD = 3;

const MIN_NAME_LETTERS = 4;
// Middle initials the PDF prints but the stored name omits ("Scott M. Lundberg").
const MAX_SKIPPED_INITIALS = 2;

// Letters NFKD leaves alone but authors' names are often stored without.
const FOLDED: Record<string, string> = { ł: "l", ø: "o", đ: "d", ð: "d", ı: "i", ß: "ss", æ: "ae", œ: "oe", þ: "th" };

function letters(value: string): string {
  return value.normalize("NFKD").toLocaleLowerCase().replace(/[^\p{L}]/gu, "")
    .replace(/[łøđðıßæœþ]/g, (letter) => FOLDED[letter]);
}

function separator(character: string): number {
  if (/[\p{M}\p{Sk}'’ʼ\-‐‑]/u.test(character)) return JOINER;
  if (/[\s.]/u.test(character)) return SPACE;
  return HARD;
}

interface NameWord {
  letters: string;
  capitalized: boolean;
}

interface NamePattern {
  authorId: string;
  words: NameWord[];
}

function nameWords(words: string[]): NameWord[] | null {
  const parsed = words
    .map((word) => ({ letters: letters(word), capitalized: /^\P{L}*\p{Lu}/u.test(word) }))
    .filter((word) => word.letters);
  const length = parsed.reduce((total, word) => total + word.letters.length, 0);
  return parsed.length >= 2 && length >= MIN_NAME_LETTERS ? parsed : null;
}

// The spellings that may link an author: the stored name, and the name without
// middle initials. A spelling two of the paper's authors share links neither.
function authorPatterns(authors: PdfAuthor[]): NamePattern[] {
  const owners = new Map<string, NamePattern | null>();
  for (const author of authors) {
    const words = author.name.split(/[\s.]+/).filter(Boolean);
    const withoutInitials = words.filter((word, index) => index === 0 || index === words.length - 1 || letters(word).length > 1);
    const keys = new Set<string>();
    for (const spelling of [words, withoutInitials]) {
      const parsed = nameWords(spelling);
      if (!parsed) continue;
      const key = parsed.map((word) => word.letters).join(" ");
      if (keys.has(key)) continue;
      keys.add(key);
      const owner = owners.get(key);
      owners.set(key, owner === undefined ? { authorId: author.id, words: parsed } : owner?.authorId === author.id ? owner : null);
    }
  }
  return [...owners.values()].filter((pattern) => pattern !== null);
}

/**
 * Finds the paper's own authors, by full name, in page text. A match needs each
 * word of the name, in order, as whole words with the stored capitalization
 * (ignoring accents), and nothing between them but spaces, hyphens, and at most
 * a couple of middle initials. Punctuation such as a comma or an email's `@`
 * never sits inside or next to a match.
 */
export function findPdfAuthorNames(runs: PdfTextRun[], authors: PdfAuthor[]): PdfAuthorMatch[] {
  const patterns = authorPatterns(authors);
  if (!patterns.length) return [];
  const text: string[] = [];
  const upper: boolean[] = [];
  // gaps[i] separates letter i from the one before it; email[i] marks an `@` there.
  const gaps: number[] = [];
  const email: boolean[] = [];
  const starts: PdfTextPosition[] = [];
  const ends: PdfTextPosition[] = [];
  let gap = HARD;
  let at = false;
  runs.forEach((run, runIndex) => {
    if (runIndex > 0 && run.item !== runs[runIndex - 1].item) gap = Math.max(gap, SPACE);
    for (let offset = 0; offset < run.text.length;) {
      const character = String.fromCodePoint(run.text.codePointAt(offset)!);
      const next = offset + character.length;
      const found = /\p{L}/u.test(character) ? letters(character) : "";
      if (found) {
        for (const letter of found) {
          text.push(letter);
          upper.push(character !== character.toLocaleLowerCase());
          gaps.push(gap);
          email.push(at);
          starts.push({ run: runIndex, offset });
          ends.push({ run: runIndex, offset: next });
          gap = NONE;
          at = false;
        }
      } else {
        gap = Math.max(gap, separator(character));
        at ||= character === "@";
      }
      offset = next;
    }
  });
  gaps.push(HARD);
  email.push(at);
  const page = text.join("");
  const wordAt = (position: number, word: NameWord) => {
    if (!page.startsWith(word.letters, position) || (word.capitalized && !upper[position])) return false;
    for (let index = position + 1; index < position + word.letters.length; index += 1) {
      if (gaps[index] === HARD) return false;
    }
    return true;
  };
  const initialAt = (position: number) => gaps[position] === SPACE && upper[position] && gaps[position + 1] === SPACE;
  // The exclusive end of the name starting at `from`, or -1.
  const matchEnd = (pattern: NamePattern, from: number) => {
    if (gaps[from] < SPACE || email[from]) return -1;
    let position = from;
    for (const [index, word] of pattern.words.entries()) {
      if (index > 0) {
        if (gaps[position] === NONE || gaps[position] === HARD) return -1;
        for (let skipped = 0; skipped < MAX_SKIPPED_INITIALS && !wordAt(position, word) && initialAt(position); skipped += 1) {
          position += 1;
        }
      }
      if (!wordAt(position, word)) return -1;
      position += word.letters.length;
    }
    return gaps[position] >= SPACE && !email[position] ? position : -1;
  };
  const matches: (PdfAuthorMatch & { from: number; to: number })[] = [];
  for (const pattern of patterns) {
    const first = pattern.words[0].letters;
    for (let from = page.indexOf(first); from >= 0; from = page.indexOf(first, from + 1)) {
      const to = matchEnd(pattern, from);
      if (to > from && !matches.some((match) => match.authorId === pattern.authorId && match.from === from)) matches.push({ authorId: pattern.authorId, start: starts[from], end: ends[to - 1], from, to });
    }
  }
  // Where two authors' names overlap, only a strictly longer one survives.
  return matches
    .filter((match) => !matches.some((other) => other.authorId !== match.authorId
      && other.from < match.to && match.from < other.to
      && other.to - other.from >= match.to - match.from))
    .sort((a, b) => a.from - b.from)
    .map(({ authorId, start, end }) => ({ authorId, start, end }));
}

export interface PdfAuthorBox {
  authorId: string;
  /** Page 0–1000 grid: x0, y0, x1, y1. */
  box: number[];
}

// Where the paper's authors' names sit in a rendered text layer, one box per
// line a name occupies. A text item is a span; search highlights split one
// item's text across `mark` elements without starting a new item.
export function pdfAuthorBoxes(layer: Element, authors: PdfAuthor[]): PdfAuthorBox[] {
  const textLayer = layer.querySelector(".textLayer");
  if (!textLayer || !authors.length) return [];
  const nodes: Text[] = [];
  const runs: PdfTextRun[] = [];
  const items = new Map<Element, number>();
  const walker = document.createTreeWalker(textLayer, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode() as Text | null; node; node = walker.nextNode() as Text | null) {
    const parent = node.parentElement;
    const item = parent?.tagName === "MARK" ? parent.parentElement : parent;
    if (!item) continue;
    if (!items.has(item)) items.set(item, items.size);
    nodes.push(node);
    runs.push({ text: node.data, item: items.get(item)! });
  }
  const bounds = layer.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return [];
  const grid = (value: number, start: number, size: number) => Math.round((value - start) / size * 1000);
  return findPdfAuthorNames(runs, authors).flatMap(({ authorId, start, end }) => {
    const range = document.createRange();
    range.setStart(nodes[start.run], start.offset);
    range.setEnd(nodes[end.run], end.offset);
    const lines: DOMRect[] = [];
    for (const rect of range.getClientRects()) {
      if (!rect.width || !rect.height) continue;
      const line = lines.find((other) => rect.top < other.bottom && other.top < rect.bottom);
      if (!line) lines.push(DOMRect.fromRect(rect));
      else {
        const left = Math.min(line.left, rect.left);
        const top = Math.min(line.top, rect.top);
        lines[lines.indexOf(line)] = new DOMRect(left, top, Math.max(line.right, rect.right) - left, Math.max(line.bottom, rect.bottom) - top);
      }
    }
    return lines.map((line) => ({
      authorId,
      box: [
        grid(line.left, bounds.left, bounds.width),
        grid(line.top, bounds.top, bounds.height),
        grid(line.right, bounds.left, bounds.width),
        grid(line.bottom, bounds.top, bounds.height),
      ],
    }));
  });
}
