import React from "react";

import { assetUrl } from "@/lib/apiUrl";
import {
  authorsLine,
  venueLine,
  type PaperPreviewData,
} from "@/components/paper-preview/paperPreviewData";

const FauxPaperThumb: React.FC<{ seed?: number }> = ({ seed = 0 }) => (
  <div className="paper-preview-thumb" aria-hidden="true" data-testid="faux-paper-thumb">
    <div className="paper-preview-thumb-title">
      <span />
      <span />
    </div>
    <div className="paper-preview-thumb-auth" />
    <div className="paper-preview-thumb-cols">
      <div className="paper-preview-thumb-col" />
      <div className="paper-preview-thumb-col" />
    </div>
    <div
      className="paper-preview-thumb-fig"
      style={{ top: 62 + (seed % 3) * 8 }}
    />
  </div>
);

const PaperThumb: React.FC<{
  thumbnailUrl: string | null;
  seed: number;
}> = ({ thumbnailUrl, seed }) => {
  const [errored, setErrored] = React.useState(false);
  const resolvedUrl = assetUrl(thumbnailUrl);

  React.useEffect(() => setErrored(false), [resolvedUrl]);

  if (!resolvedUrl || errored) return <FauxPaperThumb seed={seed} />;
  return (
    <div className="paper-preview-thumb paper-preview-thumb-real">
      <img
        data-testid="paper-preview-image"
        src={resolvedUrl}
        alt=""
        loading="lazy"
        decoding="async"
        onError={() => setErrored(true)}
      />
    </div>
  );
};

export const PaperPreviewCard: React.FC<{ data: PaperPreviewData }> = ({
  data,
}) => {
  const seed = data.routeId
    .split("")
    .reduce((total, character) => total + character.charCodeAt(0), 0);
  const authorText = authorsLine(data);

  return (
    <div className="paper-preview-inner">
      <PaperThumb thumbnailUrl={data.thumbnailUrl} seed={seed} />
      <div className="paper-preview-meta">
        <div className="paper-preview-title">{data.title}</div>
        {authorText && <div className="paper-preview-auth">{authorText}</div>}
        <div className="paper-preview-venue">
          {venueLine(data)}
          {data.arxivId && <> · arXiv:{data.arxivId}</>}
          {data.citationCount != null && (
            <> · ↑ {data.citationCount.toLocaleString()}</>
          )}
        </div>
        {data.tasks.length > 0 && (
          <div className="paper-preview-tags">
            {data.tasks.map((task) => (
              <span
                key={task.slug || task.name}
                className="paper-preview-tag"
              >
                {task.name}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
