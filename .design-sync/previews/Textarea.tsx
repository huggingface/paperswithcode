import * as React from "react";
import { Textarea, Label } from "paperswithcode";

const col: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 8,
  padding: 20,
  width: 380,
};

export function LabeledAbstract() {
  return (
    <div style={col}>
      <Label htmlFor="abstract">Abstract</Label>
      <Textarea
        id="abstract"
        rows={5}
        defaultValue={
          "We present a deep residual learning framework to ease the training of networks that are substantially deeper than those used previously. We explicitly reformulate the layers as learning residual functions with reference to the layer inputs."
        }
      />
    </div>
  );
}

export function Placeholder() {
  return (
    <div style={col}>
      <Label htmlFor="notes">Reproduction notes</Label>
      <Textarea id="notes" placeholder="Describe the training setup, hardware, and hyperparameters…" />
    </div>
  );
}

export function Disabled() {
  return (
    <div style={col}>
      <Label htmlFor="frozen" style={{ opacity: 0.5 }}>
        Review comments (locked)
      </Label>
      <Textarea
        id="frozen"
        disabled
        defaultValue="This submission has been accepted to NeurIPS 2017 and can no longer be edited."
      />
    </div>
  );
}
