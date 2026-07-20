import * as React from "react";
import { Toggle } from "paperswithcode";
import { Star, Bookmark } from "lucide-react";

const row: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 12,
  padding: 20,
};

export function VariantsAndStates() {
  return (
    <div style={row}>
      <Toggle aria-label="Default">Default</Toggle>
      <Toggle defaultPressed aria-label="Pressed">
        Pressed
      </Toggle>
      <Toggle variant="outline" aria-label="Outline">
        Outline
      </Toggle>
      <Toggle disabled aria-label="Disabled">
        Disabled
      </Toggle>
    </div>
  );
}

export function WithIcons() {
  return (
    <div style={row}>
      <Toggle defaultPressed aria-label="Star paper">
        <Star style={{ height: 16, width: 16, marginRight: 6 }} />
        Star
      </Toggle>
      <Toggle variant="outline" aria-label="Bookmark paper">
        <Bookmark style={{ height: 16, width: 16, marginRight: 6 }} />
        Bookmark
      </Toggle>
    </div>
  );
}
