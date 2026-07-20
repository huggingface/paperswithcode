import * as React from "react";
import { Separator } from "paperswithcode";

export function PaperMetadata() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: 20, width: 380 }}>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600 }}>Deep Residual Learning for Image Recognition</div>
        <div style={{ fontSize: 13, color: "hsl(var(--muted-foreground))" }}>
          He, Zhang, Ren, Sun · CVPR 2016
        </div>
      </div>
      <Separator />
      <div style={{ fontSize: 13, color: "hsl(var(--muted-foreground))" }}>
        Introduces residual connections enabling networks of 100+ layers.
      </div>
    </div>
  );
}

export function InlineStats() {
  return (
    <div style={{ display: "flex", height: 20, alignItems: "center", gap: 12, padding: 20, fontSize: 13 }}>
      <span>124 benchmarks</span>
      <Separator orientation="vertical" />
      <span>38 datasets</span>
      <Separator orientation="vertical" />
      <span>1,204 papers</span>
    </div>
  );
}
