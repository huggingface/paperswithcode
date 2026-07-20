import * as React from "react";
import { Progress } from "paperswithcode";

const col: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 20,
  padding: 20,
};

const labelRow: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  fontSize: 13,
  marginBottom: 6,
};

export function BenchmarkCompletion() {
  return (
    <div style={col}>
      <div style={{ width: 280 }}>
        <div style={labelRow}>
          <span>ImageNet evaluation</span>
          <span style={{ color: "hsl(var(--muted-foreground))" }}>25%</span>
        </div>
        <Progress value={25} />
      </div>
      <div style={{ width: 280 }}>
        <div style={labelRow}>
          <span>COCO detection</span>
          <span style={{ color: "hsl(var(--muted-foreground))" }}>60%</span>
        </div>
        <Progress value={60} />
      </div>
      <div style={{ width: 280 }}>
        <div style={labelRow}>
          <span>SQuAD 2.0</span>
          <span style={{ color: "hsl(var(--muted-foreground))" }}>100%</span>
        </div>
        <Progress value={100} />
      </div>
    </div>
  );
}

export function TrainingProgress() {
  return (
    <div style={col}>
      <div style={{ width: 280 }}>
        <div style={labelRow}>
          <span>Training epoch 72 / 100</span>
          <span style={{ color: "hsl(var(--muted-foreground))" }}>72%</span>
        </div>
        <Progress value={72} />
      </div>
    </div>
  );
}
