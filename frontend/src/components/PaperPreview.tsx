import React from "react";

// Hand-drawn PDF preview (fallback when no real thumbnail exists)

const seedRand = (seed: string): (() => number) => {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  }
  return () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    h ^= h >>> 16;
    return ((h >>> 0) % 10000) / 10000;
  };
};

const PdfThumbnail: React.FC<{ paperId: string }> = ({ paperId }) => {
  const rand = seedRand(paperId);
  const W = 160;
  const H = 220;
  const titleLines = [0.85 + rand() * 0.1, 0.55 + rand() * 0.25];
  const authorW = 0.45 + rand() * 0.3;
  const colLines: number[] = [];
  const numLines = 9 + Math.floor(rand() * 3);
  for (let i = 0; i < numLines; i++) colLines.push(0.55 + rand() * 0.4);
  const hasFigure = rand() > 0.3;
  const figureType = Math.floor(rand() * 3);
  const rightLines: number[] = [];
  const rightCount = 6 + Math.floor(rand() * 3);
  for (let i = 0; i < rightCount; i++) rightLines.push(0.5 + rand() * 0.45);

  const lineColor = "#9A9588";
  const titleColor = "#3A352D";
  const padding = 5;
  const colWidth = (W - padding * 2 - 2) / 2;
  const colLeft = padding;
  const colRight = padding + colWidth + 2;

  let y = padding + 2;
  const titleY = y;
  y += 4 + 2;
  const authorsY = y + 1;
  y += 5;
  const stampY = y;
  y += 3;
  const bodyTop = y + 1;

  return (
    <div
      style={{
        width: W,
        height: H,
        background: "#FDFCF9",
        border: "1px solid var(--hairline-strong)",
        borderRadius: 2,
        boxShadow: "0 1px 0 rgba(0,0,0,0.04), 0 4px 8px -4px rgba(0,0,0,0.08)",
        flexShrink: 0,
        overflow: "hidden",
        position: "relative",
      }}
    >
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
        {titleLines.map((w, i) => (
          <rect
            key={`t${i}`}
            x={padding + ((W - padding * 2) * (1 - w)) / 2}
            y={titleY + i * 2.4}
            width={(W - padding * 2) * w}
            height={1.4}
            fill={titleColor}
            rx={0.3}
          />
        ))}
        <rect
          x={padding + ((W - padding * 2) * (1 - authorW)) / 2}
          y={authorsY}
          width={(W - padding * 2) * authorW}
          height={0.9}
          fill={lineColor}
          opacity={0.7}
          rx={0.2}
        />
        <rect x={padding} y={stampY} width={6} height={1} fill={titleColor} opacity={0.6} />
        {colLines.map((w, i) => {
          const ly = bodyTop + i * 2.1;
          if (ly > H - padding - 1) return null;
          return (
            <rect
              key={`l${i}`}
              x={colLeft}
              y={ly}
              width={colWidth * w}
              height={0.8}
              fill={lineColor}
              opacity={0.55}
              rx={0.2}
            />
          );
        })}
        {hasFigure && (
          <g>
            <rect
              x={colRight}
              y={bodyTop}
              width={colWidth}
              height={14}
              fill="#F0EBE0"
              stroke={lineColor}
              strokeWidth={0.3}
              opacity={0.9}
            />
            {figureType === 0 && (
              <g stroke={titleColor} strokeWidth={0.4} fill="none" opacity={0.6}>
                <polyline
                  points={`${colRight + 2},${bodyTop + 11} ${colRight + 6},${bodyTop + 8} ${colRight + 10},${bodyTop + 9} ${colRight + 14},${bodyTop + 5} ${colRight + 18},${bodyTop + 6} ${colRight + 22},${bodyTop + 3}`}
                />
              </g>
            )}
            {figureType === 1 && (
              <g opacity={0.55}>
                <circle cx={colRight + colWidth / 2} cy={bodyTop + 7} r={3.5} fill={titleColor} />
                <rect x={colRight + 2} y={bodyTop + 11} width={colWidth - 4} height={1.5} fill={lineColor} />
              </g>
            )}
            {figureType === 2 && (
              <g opacity={0.55}>
                <rect x={colRight + 3} y={bodyTop + 5} width={colWidth - 6} height={1} fill={titleColor} />
                <rect x={colRight + 6} y={bodyTop + 8} width={colWidth - 12} height={0.8} fill={titleColor} />
              </g>
            )}
          </g>
        )}
        {rightLines.map((w, i) => {
          const ly = bodyTop + (hasFigure ? 16 : 0) + i * 2.1;
          if (ly > H - padding - 1) return null;
          return (
            <rect
              key={`r${i}`}
              x={colRight}
              y={ly}
              width={colWidth * w}
              height={0.8}
              fill={lineColor}
              opacity={0.55}
              rx={0.2}
            />
          );
        })}
      </svg>
    </div>
  );
};

/**
 * Real paper thumbnail wrapper. Prefers the backend-supplied thumbnail_url;
 * falls back to the hand-drawn PdfThumbnail when no image is available.
 */
export const PaperPreview: React.FC<{ paperId: string; title: string; thumbnailUrl: string | null; priority?: boolean }> = ({
  paperId,
  title,
  thumbnailUrl,
  priority = false,
}) => {
  const [errored, setErrored] = React.useState(false);
  const [imgAttempt, setImgAttempt] = React.useState(0);
  const [shouldLoad, setShouldLoad] = React.useState(priority);
  const containerRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    setErrored(false);
    setImgAttempt(0);
  }, [thumbnailUrl]);

  const resolvedThumbnailUrl = React.useMemo(() => {
    if (!thumbnailUrl) return null;
    if (imgAttempt === 0) return thumbnailUrl;
    const separator = thumbnailUrl.includes("?") ? "&" : "?";
    return `${thumbnailUrl}${separator}retry=${imgAttempt}`;
  }, [thumbnailUrl, imgAttempt]);

  React.useEffect(() => {
    if (priority || shouldLoad) return;
    const node = containerRef.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShouldLoad(true);
          observer.disconnect();
        }
      },
      { rootMargin: "250px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [priority, shouldLoad]);

  if (thumbnailUrl && !errored) {
    return (
      <div
        ref={containerRef}
        style={{
          width: 160,
          height: 220,
          background: "#FDFCF9",
          border: "1px solid var(--hairline-strong)",
          borderRadius: 2,
          boxShadow: "0 1px 0 rgba(0,0,0,0.04), 0 4px 8px -4px rgba(0,0,0,0.08)",
          flexShrink: 0,
          overflow: "hidden",
          position: "relative",
        }}
      >
        {(priority || shouldLoad) && resolvedThumbnailUrl && (
          <img
            key={resolvedThumbnailUrl}
            src={resolvedThumbnailUrl}
            alt={`Thumbnail for ${title}`}
            loading={priority ? "eager" : "lazy"}
            decoding="async"
            fetchPriority={priority ? "high" : "auto"}
            style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
            onError={() => {
              if (imgAttempt < 1) {
                setImgAttempt((n) => n + 1);
                return;
              }
              setErrored(true);
            }}
          />
        )}
      </div>
    );
  }
  return <PdfThumbnail paperId={paperId} />;
};
