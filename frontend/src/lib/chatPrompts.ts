export const SUGGESTED_CHAT_PROMPTS = [
  "What are decision models?",
  "Find relevant papers on RLVR",
  "What's the state-of-the-art for real-time object detection?",
] as const;

// Returns the rest of the first suggested prompt that `text` starts, ignoring
// case, or "" when the text does not begin any suggestion.
export const completeSuggestedChatPrompt = (text: string): string => {
  if (!text) return "";
  const typed = text.toLowerCase();
  const prompt = SUGGESTED_CHAT_PROMPTS.find(
    (candidate) => candidate.length > text.length && candidate.toLowerCase().startsWith(typed),
  );
  return prompt ? prompt.slice(text.length) : "";
};
