import React from "react";

import { Skeleton } from "@/components/ui/skeleton";

/** One titled group of directory tiles, e.g. an area's tasks. */
export const AreaSection: React.FC<{
  id?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  meta: React.ReactNode;
  style?: React.CSSProperties;
  children: React.ReactNode;
}> = ({ id, title, description, meta, style, children }) => (
  <section id={id} className="area-section" style={style}>
    <div className="area-section-head">
      <div>
        <h2 className="area-section-title">{title}</h2>
        {description && <div className="area-section-description">{description}</div>}
      </div>
      <div className="area-section-meta">{meta}</div>
    </div>
    <div className="tag-grid">{children}</div>
  </section>
);

export const AreaDirectorySkeleton: React.FC<{
  sections?: number;
  tiles: number;
  tileClassName: string;
}> = ({ sections = 4, tiles, tileClassName }) => (
  <div className="area-directory-skeleton">
    {Array.from({ length: sections }).map((_, i) => (
      <div key={i}>
        <Skeleton className="h-8 w-1/3 mb-4" />
        <div className="tag-grid">
          {Array.from({ length: tiles }).map((__, j) => (
            <Skeleton key={j} className={tileClassName} />
          ))}
        </div>
      </div>
    ))}
  </div>
);

/** "N tasks across M areas." under a task directory. */
export const AreaDirectoryFooter: React.FC<{ areas: ReadonlyArray<{ tasks: readonly unknown[] }> }> = ({
  areas,
}) => {
  const populated = areas.filter((area) => area.tasks.length > 0);
  const totalTasks = populated.reduce((sum, area) => sum + area.tasks.length, 0);
  if (totalTasks === 0) return null;
  return (
    <div className="area-directory-footer">
      {totalTasks} tasks across {populated.length} areas.
    </div>
  );
};
