export const SUGGESTED_CHAT_PROMPTS = [
  "What are decision models?",
  "Find relevant papers on RLVR",
  "What's the state-of-the-art for real-time object detection?",
] as const;

// Openings Tab completes before the visitor reaches a catalog name.
const QUESTION_STARTERS = [
  ...SUGGESTED_CHAT_PROMPTS,
  "What are the latest papers on ",
  "Which benchmarks are used for ",
  "Which methods work best for ",
  "How does ",
  "Explain how ",
  "Compare ",
  "Summarize the key contributions of ",
] as const;

// A catalog name may be completed from up to this many trailing words.
const MAX_FRAGMENT_WORDS = 4;
// A lone word needs more typed characters than a phrase before it is completed.
const MIN_PHRASE_CHARS = 3;
const MIN_WORD_CHARS = 4;
// Single words that start catalog names but are far more often plain English.
const COMMON_WORDS = new Set([
  "about", "all", "and", "are", "best", "can", "compare", "does", "explain",
  "find", "for", "from", "give", "how", "into", "latest", "list", "method",
  "methods", "model", "models", "new", "paper", "papers", "recent", "show",
  "state", "summarize", "task", "tasks", "the", "this", "use", "what", "when",
  "where", "which", "who", "why", "with", "work",
]);
// Positions where a word starts: after whitespace, an opening bracket, or a quote.
const WORD_START = /(?:^|(?<=[\s("'“‘]))(?=\S)/g;

const completeStarter = (text: string): string => {
  const typed = text.toLowerCase();
  const starter = QUESTION_STARTERS.find(
    (candidate) => candidate.length > text.length && candidate.toLowerCase().startsWith(typed),
  );
  return starter ? starter.slice(text.length) : "";
};

const completeCatalogName = (text: string, vocabulary: readonly string[]): string => {
  const starts = [...text.matchAll(WORD_START)].map((match) => match.index ?? 0);
  // Longest trailing phrase first, so "object det" beats a name starting "det".
  for (const start of starts.slice(-MAX_FRAGMENT_WORDS)) {
    const fragment = text.slice(start);
    const lower = fragment.toLowerCase();
    const phrase = /\s/.test(fragment);
    if (fragment.length < (phrase ? MIN_PHRASE_CHARS : MIN_WORD_CHARS)) continue;
    if (!phrase && COMMON_WORDS.has(lower)) continue;
    const name = vocabulary.find(
      (candidate) => candidate.length > fragment.length && candidate.toLowerCase().startsWith(lower),
    );
    if (name) return name.slice(fragment.length);
  }
  return "";
};

// Returns the text Tab would append: the rest of a question starter the text
// begins, else the rest of the most used task, method, or benchmark name its
// last words begin, else "". Nothing is offered after trailing whitespace.
export const completeChatText = (text: string, vocabulary: readonly string[]): string => {
  if (!text.trim() || /\s$/.test(text)) return "";
  return completeStarter(text) || completeCatalogName(text, vocabulary);
};
