import * as React from "react";
import { Input, Label } from "paperswithcode";
import { Search } from "lucide-react";

const col: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 8,
  padding: 20,
  width: 340,
};

export function LabeledSearch() {
  return (
    <div style={col}>
      <Label htmlFor="paper-search">Search papers</Label>
      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
        <Search
          size={16}
          style={{
            position: "absolute",
            left: 10,
            color: "hsl(var(--muted-foreground))",
          }}
        />
        <Input id="paper-search" placeholder="Search 1M+ papers…" style={{ paddingLeft: 32 }} />
      </div>
    </div>
  );
}

export function States() {
  return (
    <div style={{ ...col, width: 320 }}>
      <Input placeholder="Filter by task…" />
      <Input defaultValue="Semantic Segmentation" />
      <Input placeholder="Archived index (unavailable)" disabled />
    </div>
  );
}

export function Types() {
  return (
    <div style={{ ...col, width: 320 }}>
      <Label htmlFor="author-email">Author email</Label>
      <Input id="author-email" type="email" placeholder="researcher@lab.edu" />
      <Label htmlFor="api-key">API key</Label>
      <Input id="api-key" type="password" defaultValue="pwc-secret-token" />
    </div>
  );
}
