import React from "react";

// Inline icons (size-restricted SVG paths)

interface IconProps {
  name:
    | "search"
    | "arrowUp"
    | "arrowLeft"
    | "arrowRight"
    | "external"
    | "github"
    | "citation"
    | "bookmark"
    | "chart"
    | "chat"
    | "pdf"
    | "copy"
    | "sparkle"
    | "user"
    | "globe"
    | "menu"
    | "close"
    | "pencil";
  size?: number;
}

export const Icon: React.FC<IconProps> = ({ name, size = 14 }) => {
  const paths: Record<IconProps["name"], React.ReactNode> = {
    search: <path d="M11 11l3 3M7 12.5a5.5 5.5 0 110-11 5.5 5.5 0 010 11z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />,
    arrowUp: <path d="M8 3l5 6H3l5-6z" fill="currentColor" />,
    arrowLeft: <path d="M9 3l-4 5 4 5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
    arrowRight: <path d="M7 3l4 5-4 5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
    external: <path d="M5 3h-2v8h8v-2M9 3h3v3M7 9l5-5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
    github: <path d="M8 1a7 7 0 00-2.21 13.64c.35.06.48-.15.48-.34v-1.2c-1.95.42-2.36-.94-2.36-.94-.32-.81-.78-1.03-.78-1.03-.64-.43.05-.43.05-.43.7.05 1.07.72 1.07.72.62 1.07 1.64.76 2.04.58.06-.45.24-.76.44-.94-1.55-.18-3.18-.78-3.18-3.46 0-.76.27-1.39.72-1.88-.07-.18-.31-.89.07-1.86 0 0 .59-.19 1.92.72.56-.15 1.16-.23 1.75-.24.59 0 1.19.08 1.75.24 1.33-.9 1.92-.72 1.92-.72.38.97.14 1.68.07 1.86.45.49.72 1.12.72 1.88 0 2.69-1.64 3.28-3.19 3.45.25.22.48.65.48 1.32v1.95c0 .19.13.41.49.34A7 7 0 008 1z" fill="currentColor" />,
    citation: <path d="M3 4h3v3H3zM4 7v1.5a1.5 1.5 0 01-1.5 1.5M9 4h3v3H9zM10 7v1.5a1.5 1.5 0 01-1.5 1.5" stroke="currentColor" strokeWidth="1.2" fill="none" />,
    bookmark: <path d="M4 2h8v12l-4-3-4 3V2z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round" />,
    chart: <path d="M2 13h12M3 11l3-4 3 2 4-5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
    chat: <path d="M3 3h10v7H7l-3 3v-3H3V3z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round" />,
    pdf: <path d="M5 2h5l3 3v9H5V2z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round" />,
    copy: <path d="M5 5h7v8H5V5zM3 3h7v2M3 3v8h2" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinejoin="round" />,
    sparkle: <path d="M8 2l1.2 3.8L13 7l-3.8 1.2L8 12l-1.2-3.8L3 7l3.8-1.2L8 2z" fill="currentColor" />,
    user: <path d="M8 8a3 3 0 100-6 3 3 0 000 6zM2 14c0-3 2.5-5 6-5s6 2 6 5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />,
    globe: <path d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM1.5 8h13M8 1.5c1.7 1.9 2.6 4.2 2.6 6.5s-.9 4.6-2.6 6.5M8 1.5C6.3 3.4 5.4 5.7 5.4 8s.9 4.6 2.6 6.5" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" />,
    menu: <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />,
    close: <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />,
    pencil: <path d="M10.5 2.5l3 3L6 13H3v-3l7.5-7.5zM9 4l3 3" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
  };
  return (
    <svg className={size === 11 ? "icon-sm" : "icon"} viewBox="0 0 16 16" width={size} height={size}>
      {paths[name]}
    </svg>
  );
};
