import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

import { MarkdownBody, type MarkdownTextProps } from './MarkdownText';

const MathMarkdownText = (props: MarkdownTextProps) => (
  <MarkdownBody {...props} rehypePlugins={[rehypeKatex]} />
);

export default MathMarkdownText;
