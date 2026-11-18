/** True when Markdown may hold inline or display math for remark-math/KaTeX. */
export function mightContainMath(text: string): boolean {
  return /\$|\\\(|\\\[/.test(text);
}
