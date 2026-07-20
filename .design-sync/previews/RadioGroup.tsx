import * as React from "react";
import { RadioGroup, RadioGroupItem, Label } from "paperswithcode";

const wrap: React.CSSProperties = { padding: 20 };
const item: React.CSSProperties = { display: "flex", alignItems: "center", gap: 8 };

export function EvaluationSplit() {
  return (
    <div style={wrap}>
      <RadioGroup defaultValue="test">
        <div style={item}>
          <RadioGroupItem value="test" id="split-test" />
          <Label htmlFor="split-test">Test</Label>
        </div>
        <div style={item}>
          <RadioGroupItem value="validation" id="split-val" />
          <Label htmlFor="split-val">Validation</Label>
        </div>
        <div style={item}>
          <RadioGroupItem value="dev" id="split-dev" />
          <Label htmlFor="split-dev">Dev</Label>
        </div>
      </RadioGroup>
    </div>
  );
}

export function ModelBackbone() {
  return (
    <div style={wrap}>
      <RadioGroup defaultValue="vit-l">
        <div style={item}>
          <RadioGroupItem value="resnet-50" id="bb-resnet" />
          <Label htmlFor="bb-resnet">ResNet-50</Label>
        </div>
        <div style={item}>
          <RadioGroupItem value="vit-b" id="bb-vitb" />
          <Label htmlFor="bb-vitb">ViT-B/16</Label>
        </div>
        <div style={item}>
          <RadioGroupItem value="vit-l" id="bb-vitl" />
          <Label htmlFor="bb-vitl">ViT-L/14</Label>
        </div>
      </RadioGroup>
    </div>
  );
}
