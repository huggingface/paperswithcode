import * as React from "react";
import { Skeleton } from "paperswithcode";

export function PaperCard() {
  return (
    <div style={{ display: "flex", gap: 16, padding: 20, width: 400 }}>
      <Skeleton style={{ borderRadius: "9999px", width: 40, height: 40 }} />
      <div style={{ display: "flex", flexDirection: "column", gap: 10, flex: 1 }}>
        <Skeleton style={{ width: "85%", height: 16 }} />
        <Skeleton style={{ width: "60%", height: 12 }} />
        <Skeleton style={{ width: "100%", height: 12 }} />
        <Skeleton style={{ width: "40%", height: 12 }} />
      </div>
    </div>
  );
}

export function LeaderboardRows() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: 20, width: 380 }}>
      {[0, 1, 2].map((i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Skeleton style={{ width: 24, height: 24, borderRadius: 6 }} />
          <Skeleton style={{ flex: 1, height: 14 }} />
          <Skeleton style={{ width: 48, height: 14 }} />
        </div>
      ))}
    </div>
  );
}

export function Thumbnail() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: 20, width: 260 }}>
      <Skeleton style={{ width: "100%", height: 140, borderRadius: 8 }} />
      <Skeleton style={{ width: "70%", height: 16 }} />
      <Skeleton style={{ width: "45%", height: 12 }} />
    </div>
  );
}
