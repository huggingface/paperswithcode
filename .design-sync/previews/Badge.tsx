import * as React from "react";
import { Badge } from "paperswithcode";

const row: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  gap: 8,
  padding: 20,
};

export function Variants() {
  return (
    <div style={row}>
      <Badge>Image Classification</Badge>
      <Badge variant="secondary">Computer Vision</Badge>
      <Badge variant="destructive">Retracted</Badge>
      <Badge variant="outline">Preprint</Badge>
    </div>
  );
}

export function PaperTags() {
  return (
    <div style={row}>
      <Badge>SOTA</Badge>
      <Badge variant="secondary">Semantic Segmentation</Badge>
      <Badge variant="secondary">Object Detection</Badge>
      <Badge variant="outline">NeurIPS 2017</Badge>
      <Badge variant="outline">arXiv</Badge>
    </div>
  );
}

export function BenchmarkRank() {
  return (
    <div style={row}>
      <Badge>#1 on ImageNet</Badge>
      <Badge variant="secondary">Top 76.5% acc</Badge>
      <Badge variant="destructive">Below baseline</Badge>
    </div>
  );
}
