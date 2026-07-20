import * as React from "react";
import { Checkbox, Label } from "paperswithcode";

const col: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 16,
  padding: 20,
};

const item: React.CSSProperties = { display: "flex", alignItems: "center", gap: 8 };

export function States() {
  return (
    <div style={{ ...col, flexDirection: "row", alignItems: "center" }}>
      <Checkbox aria-label="Unchecked" />
      <Checkbox defaultChecked aria-label="Checked" />
      <Checkbox disabled aria-label="Disabled" />
      <Checkbox disabled defaultChecked aria-label="Disabled checked" />
    </div>
  );
}

export function WithLabels() {
  return (
    <div style={col}>
      <div style={item}>
        <Checkbox id="cv" defaultChecked />
        <Label htmlFor="cv">Computer Vision</Label>
      </div>
      <div style={item}>
        <Checkbox id="nlp" defaultChecked />
        <Label htmlFor="nlp">Natural Language Processing</Label>
      </div>
      <div style={item}>
        <Checkbox id="rl" />
        <Label htmlFor="rl">Reinforcement Learning</Label>
      </div>
      <div style={item}>
        <Checkbox id="deprecated" disabled />
        <Label htmlFor="deprecated" style={{ opacity: 0.5 }}>
          Archived (unavailable)
        </Label>
      </div>
    </div>
  );
}
