import { lazy, Suspense } from 'react';
import ReactMarkdown, { type Options } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import { Link } from 'react-router-dom';

import { PaperPreviewLink } from '@/components/paper-preview/PaperPreviewLink';
import { extractPaperRouteId, resolveInternalPath } from '@/lib/internalLinks';
import { mightContainMath } from '@/lib/markdownMath';

// KaTeX (~77 KB gzip + its CSS) loads only for text that has math delimiters.
const MathMarkdownText = lazy(() => import('./MathMarkdownText'));

export interface MarkdownTextProps {
  text: string;
  className?: string;
}

export const MarkdownBody = ({
  text,
  className = '',
  rehypePlugins,
}: MarkdownTextProps & Pick<Options, 'rehypePlugins'>) => {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={rehypePlugins}
        components={{
          a: ({ href, children, node: _node, ...props }) => {
            const internalPath = resolveInternalPath(href);
            if (internalPath) {
              const routeId = extractPaperRouteId(internalPath);
              if (routeId) {
                return (
                  <PaperPreviewLink routeId={routeId} to={internalPath} {...props}>
                    {children}
                  </PaperPreviewLink>
                );
              }
              return (
                <Link to={internalPath} {...props}>
                  {children}
                </Link>
              );
            }
            return (
              <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                {children}
              </a>
            );
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
};

const MarkdownText = (props: MarkdownTextProps) => {
  if (!mightContainMath(props.text)) return <MarkdownBody {...props} />;
  return (
    <Suspense fallback={<MarkdownBody {...props} />}>
      <MathMarkdownText {...props} />
    </Suspense>
  );
};

export default MarkdownText;
