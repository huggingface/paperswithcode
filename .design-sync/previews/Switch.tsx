import * as React from "react";
import { Switch, Label } from "paperswithcode";

const settingsCol: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 16,
  padding: 20,
  width: 380,
};

const settingRow: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 16,
};

export function States() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 20, padding: 20 }}>
      <Switch aria-label="Off" />
      <Switch defaultChecked aria-label="On" />
      <Switch disabled aria-label="Disabled" />
      <Switch disabled defaultChecked aria-label="Disabled on" />
    </div>
  );
}

export function NotificationSettings() {
  return (
    <div style={settingsCol}>
      <div style={settingRow}>
        <Label htmlFor="sota-alerts">Email me about new SOTA results</Label>
        <Switch id="sota-alerts" defaultChecked />
      </div>
      <div style={settingRow}>
        <Label htmlFor="weekly-digest">Weekly trending papers digest</Label>
        <Switch id="weekly-digest" />
      </div>
      <div style={settingRow}>
        <Label htmlFor="beta-eval" style={{ opacity: 0.5 }}>
          Beta evaluation server (coming soon)
        </Label>
        <Switch id="beta-eval" disabled />
      </div>
    </div>
  );
}
