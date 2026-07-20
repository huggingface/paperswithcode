import * as React from "react";
import { Label, Input, Switch, Checkbox } from "paperswithcode";

const col: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 8,
  padding: 20,
  width: 320,
};

const row: React.CSSProperties = { display: "flex", alignItems: "center", gap: 8 };

export function WithInput() {
  return (
    <div style={col}>
      <Label htmlFor="dataset-name">Dataset name</Label>
      <Input id="dataset-name" placeholder="ImageNet" />
    </div>
  );
}

export function WithSwitch() {
  return (
    <div style={{ ...col, gap: 16 }}>
      <div style={row}>
        <Switch id="public-leaderboard" defaultChecked />
        <Label htmlFor="public-leaderboard">Show on public leaderboard</Label>
      </div>
      <div style={row}>
        <Checkbox id="cite-official" defaultChecked />
        <Label htmlFor="cite-official">Use official evaluation code</Label>
      </div>
    </div>
  );
}
