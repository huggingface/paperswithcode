import type { Api, Model, Tool } from "@earendil-works/pi-ai";

import { gatewayPayloadLimit } from "./provider.js";

const INPUT_MARGIN_TOKENS = 8000;
const NOTICE = '<paper_context_budget_notice>Paper evidence was shortened automatically to reserve room for the answer. Paper attributes describe the originally prepared source; the excerpts below may be shorter. Each paper\'s included_bytes now counts the Markdown bytes kept here, so use pwc_read_paper with that paper\'s route_id as paper and its included_bytes as offset to retrieve omitted material. Preserve the user request and viewer orientation.</paper_context_budget_notice>\n';

interface PaperBudget {
  model: Pick<Model<Api>, "contextWindow" | "maxTokens">;
  systemPrompt: string;
  tools: Tool[];
}

// Only server-produced evidence blocks are eligible. Quoted user text and
// selection content are HTML escaped and remain outside referenced_papers.
export function fitPaperContext(prompt: string, budget: PaperBudget): string {
  if (!prompt.startsWith("<paper_context_notice>\n")) return prompt;
  const start = prompt.indexOf("<referenced_papers>\n");
  const end = prompt.indexOf("\n</referenced_papers>", start);
  if (start < 0 || end < 0) return prompt;
  const evidence = prompt.slice(start, end);
  const pattern = /(<paper_info>\n|<paper_markdown_prefix>\n)([\s\S]*?)(\n<\/paper_info>|\n<\/paper_markdown_prefix>)/gu;
  const paperPattern = /<paper ([^>]*)>([\s\S]*?)<\/paper>/gu;
  const bodies = [...evidence.matchAll(pattern)];
  if (!bodies.length) return prompt;
  const lengths = bodies.map(match => Buffer.byteLength(match[2]!));
  const total = lengths.reduce((sum, size) => sum + size, 0);
  const prefix = prompt.slice(0, start);
  const suffix = prompt.slice(end);
  const context = { systemPrompt: budget.systemPrompt, tools: budget.tools };
  const fixed = JSON.stringify(context);
  const render = (fraction: number): { prompt: string; evidenceBytes: number } => {
    let index = 0;
    let evidenceBytes = 0;
    // included_bytes is the offset a continuation read starts from, so it must
    // count the Markdown kept here, not the originally prepared prefix.
    const trimmed = evidence.replace(paperPattern, (_paper, attributes: string, inner: string) => {
      let markdownBytes = 0;
      const body = inner.replace(pattern, (_match, open: string, body: string, close: string) => {
        const limit = Math.floor(lengths[index++]! * fraction);
        let value = body;
        if (limit < Buffer.byteLength(body)) {
          // Buffer decoding can insert U+FFFD when a UTF-8 codepoint is split.
          // Trim by codepoint instead, then discard a partial HTML entity.
          let size = 0;
          const chars: string[] = [];
          for (const char of body) {
            size += Buffer.byteLength(char);
            if (size > limit) break;
            chars.push(char);
          }
          value = chars.join("").replace(/&[^;\s]*$/u, "");
        }
        if (open.startsWith("<paper_markdown_prefix")) markdownBytes = Buffer.byteLength(value);
        evidenceBytes += Buffer.byteLength(value);
        return open + value + close;
      });
      const counted = attributes.replace(/included_bytes="\d+"/u, `included_bytes="${markdownBytes}"`);
      return `<paper ${counted}>${body}</paper>`;
    });
    return { prompt: prefix + NOTICE + trimmed + suffix, evidenceBytes };
  };
  const fits = (candidate: { prompt: string; evidenceBytes: number }): boolean => {
    // Treat evidence bytes as tokens, rather than assuming four characters per
    // token for equations, tables, or non-Latin text. Reserve the full output
    // allowance and headroom for framing/history; normal history compaction
    // remains responsible for previous conversation turns.
    const ordinaryBytes = Buffer.byteLength(candidate.prompt) - candidate.evidenceBytes;
    const estimated = Math.ceil((Buffer.byteLength(fixed) + ordinaryBytes) / 3)
      + candidate.evidenceBytes + budget.model.maxTokens + INPUT_MARGIN_TOKENS;
    const bytes = Buffer.byteLength(JSON.stringify({ ...context, prompt: candidate.prompt }));
    return estimated <= budget.model.contextWindow && bytes <= gatewayPayloadLimit(budget.model.contextWindow) * 0.8;
  };
  if (fits({ prompt, evidenceBytes: total })) return prompt;
  let low = 0;
  let high = 1;
  let result = render(0);
  // A too-large human request or fixed tool/system context is not paper data.
  // Preserve it for the normal context error path instead of deleting it.
  if (!fits(result)) return result.prompt;
  for (let iteration = 0; iteration < 16; iteration++) {
    const middle = (low + high) / 2;
    const candidate = render(middle);
    if (fits(candidate)) { low = middle; result = candidate; }
    else high = middle;
  }
  return result.prompt;
}
