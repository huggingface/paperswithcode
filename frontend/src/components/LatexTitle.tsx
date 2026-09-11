import { Fragment, useMemo, type ReactNode } from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';

interface LatexTextProps {
  text: string;
  className?: string;
  highlight?: string;
}

type TextToken = { type: 'text'; content: string } | { type: 'inline'; content: string } | { type: 'display'; content: string };

const SPACING_COMMANDS = new Set([',', ';', ':', '!', ' ', 'quad', 'qquad', 'enspace', 'thinspace']);

const LATEX_ACUTE: Record<string, string> = {
  a: 'á', e: 'é', i: 'í', o: 'ó', u: 'ú', y: 'ý',
  A: 'Á', E: 'É', I: 'Í', O: 'Ó', U: 'Ú', Y: 'Ý',
};

const LATEX_GRAVE: Record<string, string> = {
  a: 'à', e: 'è', i: 'ì', o: 'ò', u: 'ù',
  A: 'À', E: 'È', I: 'Ì', O: 'Ò', U: 'Ù',
};

const LATEX_CIRCUMFLEX: Record<string, string> = {
  a: 'â', e: 'ê', i: 'î', o: 'ô', u: 'û',
  A: 'Â', E: 'Ê', I: 'Î', O: 'Ô', U: 'Û',
};

const LATEX_UMLAUT: Record<string, string> = {
  a: 'ä', e: 'ë', i: 'ï', o: 'ö', u: 'ü', y: 'ÿ',
  A: 'Ä', E: 'Ë', I: 'Ï', O: 'Ö', U: 'Ü', Y: 'Ÿ',
};

const LATEX_ACCENT_BY_COMMAND: Record<string, Record<string, string>> = {
  "'": LATEX_ACUTE,
  '`': LATEX_GRAVE,
  '^': LATEX_CIRCUMFLEX,
  '"': LATEX_UMLAUT,
  '~': { n: 'ñ', N: 'Ñ' },
};

const LATEX_STANDALONE_COMMANDS: Record<string, string> = {
  ss: 'ß',
  ae: 'æ',
  AE: 'Æ',
  oe: 'œ',
  OE: 'Œ',
  o: 'ø',
  O: 'Ø',
  l: 'ł',
  L: 'Ł',
};

function applyLatexAccent(accentCommand: string, letter: string): string | null {
  return LATEX_ACCENT_BY_COMMAND[accentCommand]?.[letter] ?? null;
}

function tokenizeMathAndText(text: string): TextToken[] {
  const tokens: TextToken[] = [];
  let i = 0;
  let buf = '';

  const flush = () => {
    if (buf) {
      tokens.push({ type: 'text', content: buf });
      buf = '';
    }
  };

  while (i < text.length) {
    if (text[i] === '$' && text[i + 1] === '$') {
      flush();
      const end = text.indexOf('$$', i + 2);
      if (end === -1) {
        buf += text.slice(i);
        break;
      }
      tokens.push({ type: 'display', content: text.slice(i + 2, end) });
      i = end + 2;
      continue;
    }
    if (text[i] === '$') {
      flush();
      const end = text.indexOf('$', i + 1);
      if (end === -1) {
        buf += text.slice(i);
        break;
      }
      tokens.push({ type: 'inline', content: text.slice(i + 1, end) });
      i = end + 1;
      continue;
    }
    buf += text[i];
    i += 1;
  }

  flush();
  return tokens;
}

function readBraced(text: string, start: number): { content: string; end: number } | null {
  if (text[start] !== '{') return null;
  let depth = 0;
  for (let i = start; i < text.length; i += 1) {
    if (text[i] === '{') depth += 1;
    else if (text[i] === '}') {
      depth -= 1;
      if (depth === 0) return { content: text.slice(start + 1, i), end: i + 1 };
    }
  }
  return null;
}

function readCommandName(text: string, start: number): { name: string; end: number } {
  let i = start + 1;
  if (i >= text.length) return { name: '', end: i };
  if (!/[a-zA-Z]/.test(text[i])) return { name: text[i], end: i + 1 };
  const nameStart = i;
  while (i < text.length && /[a-zA-Z]/.test(text[i])) i += 1;
  return { name: text.slice(nameStart, i), end: i };
}

/** Read ^/_ script (braced or single-char) starting at `start`. */
function readScriptSegment(text: string, start: number): { end: number } | null {
  const scriptChar = text[start];
  if (scriptChar !== '^' && scriptChar !== '_') return null;
  if (start + 1 >= text.length) return null;

  if (text[start + 1] === '{') {
    const braced = readBraced(text, start + 1);
    if (!braced) return null;
    return { end: braced.end };
  }

  if (/[A-Za-z0-9+\-=.]/.test(text[start + 1])) {
    return { end: start + 2 };
  }

  return null;
}

/**
 * Detect title math without $ delimiters, e.g. V^{2}, x_i, H_{2}.
 * Requires a base token immediately followed by at least one ^/_ script.
 */
function readScriptedMath(text: string, start: number): { latex: string; end: number } | null {
  let i = start;

  if (text[i] === '\\') {
    const { name, end: cmdEnd } = readCommandName(text, i);
    if (!name) return null;
    i = cmdEnd;
    if (text[i] === '{') {
      const braced = readBraced(text, i);
      if (braced) i = braced.end;
    }
  } else if (/[A-Za-z0-9]/.test(text[i])) {
    let baseEnd = i + 1;
    while (baseEnd < text.length && /[A-Za-z0-9]/.test(text[baseEnd])) baseEnd += 1;
    if (text[baseEnd] !== '^' && text[baseEnd] !== '_') return null;
    i = baseEnd;
  } else {
    return null;
  }

  const mathStart = start;
  let scriptCount = 0;

  while (i < text.length) {
    const segment = readScriptSegment(text, i);
    if (!segment) break;
    scriptCount += 1;
    i = segment.end;
  }

  if (scriptCount === 0) return null;
  return { latex: text.slice(mathStart, i), end: i };
}

function literalTerms(query: string | undefined): string[] {
  return Array.from(new Set((query || "").trim().split(/\s+/).filter(Boolean)))
    .sort((a, b) => b.length - a.length);
}

function highlightText(text: string, query: string | undefined, keyPrefix: string): ReactNode[] {
  const terms = literalTerms(query);
  if (!terms.length) return [text];
  const escaped = terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const matcher = new RegExp(`(${escaped.join("|")})`, "gi");
  return text.split(matcher).filter(Boolean).map((part, index) =>
    terms.some((term) => term.toLocaleLowerCase() === part.toLocaleLowerCase())
      ? <mark key={`${keyPrefix}-mark-${index}`}>{part}</mark>
      : part
  );
}

function parseTextContent(text: string, keyPrefix: string, highlight?: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let i = 0;
  let key = 0;
  const nextKey = () => `${keyPrefix}-${key++}`;

  const wrap = (tag: 'strong' | 'em', children: ReactNode[]) => {
    if (tag === 'strong') return <strong key={nextKey()}>{children}</strong>;
    return <em key={nextKey()}>{children}</em>;
  };

  while (i < text.length) {
    if (text[i] === '\\') {
      const { name, end: cmdEnd } = readCommandName(text, i);
      i = cmdEnd;

      if (LATEX_STANDALONE_COMMANDS[name]) {
        nodes.push(LATEX_STANDALONE_COMMANDS[name]);
        continue;
      }

      if (name.length === 1 && i < text.length && /[A-Za-z]/.test(text[i])) {
        const accented = applyLatexAccent(name, text[i]);
        if (accented) {
          nodes.push(accented);
          i += 1;
          continue;
        }
      }

      if (name === 'c') {
        const braced = readBraced(text, i);
        if (braced?.content.length === 1) {
          const cedilla = { c: 'ç', C: 'Ç' }[braced.content];
          if (cedilla) {
            nodes.push(cedilla);
            i = braced.end;
            continue;
          }
        }
      }

      if (name === 'textbf' || name === 'mathbf') {
        const braced = readBraced(text, i);
        if (braced) {
          i = braced.end;
          nodes.push(wrap('strong', parseTextContent(braced.content, nextKey(), highlight)));
          continue;
        }
      }

      if (name === 'emph' || name === 'textit' || name === 'textsl' || name === 'texttt') {
        const braced = readBraced(text, i);
        if (braced) {
          i = braced.end;
          nodes.push(wrap('em', parseTextContent(braced.content, nextKey(), highlight)));
          continue;
        }
      }

      if (name === 'color' || name === 'textcolor') {
        const colorArg = readBraced(text, i);
        if (colorArg) {
          i = colorArg.end;
          const bodyArg = readBraced(text, i);
          if (bodyArg) {
            i = bodyArg.end;
            nodes.push(...parseTextContent(bodyArg.content, nextKey(), highlight));
          }
          continue;
        }
      }

      if (SPACING_COMMANDS.has(name)) {
        nodes.push(' ');
        continue;
      }

      if (name === '~') {
        nodes.push('\u00A0');
        continue;
      }

      const braced = readBraced(text, i);
      if (braced) {
        i = braced.end;
        nodes.push(...parseTextContent(braced.content, nextKey(), highlight));
        continue;
      }

      nodes.push(`\\${name}`);
      continue;
    }

    if (text[i] === '~') {
      nodes.push('\u00A0');
      i += 1;
      continue;
    }

    const scripted = readScriptedMath(text, i);
    if (scripted) {
      nodes.push(<KatexHtml key={nextKey()} latex={scripted.latex} display={false} />);
      i = scripted.end;
      continue;
    }

    let j = i;
    while (j < text.length && text[j] !== '\\' && text[j] !== '~') {
      if (readScriptedMath(text, j)) break;
      j += 1;
    }
    if (j > i) nodes.push(...highlightText(text.slice(i, j), highlight, nextKey()));
    i = j;
  }

  return nodes;
}

function KatexHtml({ latex, display }: { latex: string; display: boolean }) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(latex.trim(), {
        displayMode: display,
        throwOnError: false,
      });
    } catch {
      return null;
    }
  }, [latex, display]);

  if (!html) {
    return <>{display ? `$$${latex}$$` : `$${latex}$`}</>;
  }

  return (
    <span
      className={display ? 'katex-display' : undefined}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

function renderLatexNodes(text: string, highlight?: string): ReactNode {
  const tokens = tokenizeMathAndText(text);
  const parts: ReactNode[] = [];

  tokens.forEach((token, index) => {
    const keyPrefix = `latex-${index}`;
    if (token.type === 'text') {
      const children = parseTextContent(token.content, keyPrefix, highlight);
      if (children.length === 1) parts.push(children[0]);
      else if (children.length > 1) parts.push(<Fragment key={keyPrefix}>{children}</Fragment>);
      return;
    }
    if (token.type === 'display') {
      parts.push(<KatexHtml key={keyPrefix} latex={token.content} display />);
      return;
    }
    parts.push(<KatexHtml key={keyPrefix} latex={token.content} display={false} />);
  });

  if (parts.length === 1) return parts[0];
  return <>{parts}</>;
}

/**
 * Renders text with LaTeX math ($...$, $$...$$, and un-delimited ^{}/_{} fragments)
 * and common text-mode commands (\\textbf, \\emph, \\color, accents, spacing, ~) used in arXiv titles/abstracts.
 */
const LatexText = ({ text, className = '', highlight }: LatexTextProps) => {
  const content = useMemo(() => renderLatexNodes(text, highlight), [text, highlight]);
  return <span className={className}>{content}</span>;
};

const LatexTitle = ({ title, className = '', highlight }: { title: string; className?: string; highlight?: string }) => (
  <LatexText text={title} className={className} highlight={highlight} />
);

export default LatexTitle;
export { LatexText };
