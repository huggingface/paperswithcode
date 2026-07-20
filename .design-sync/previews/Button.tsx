import * as React from "react";
import { Button } from "paperswithcode";
import { ArrowRight, Star, Download } from "lucide-react";

const row: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  gap: 12,
  padding: 20,
};

export function Variants() {
  return (
    <div style={row}>
      <Button>Submit paper</Button>
      <Button variant="secondary">Secondary</Button>
      <Button variant="outline">Follow</Button>
      <Button variant="ghost">Ghost</Button>
      <Button variant="destructive">Remove</Button>
      <Button variant="link">View on arXiv</Button>
    </div>
  );
}

export function Sizes() {
  return (
    <div style={row}>
      <Button size="sm">Small</Button>
      <Button size="default">Default</Button>
      <Button size="lg">Large</Button>
      <Button size="icon" aria-label="Star">
        <Star />
      </Button>
    </div>
  );
}

export function WithIcons() {
  return (
    <div style={row}>
      <Button>
        Get code <ArrowRight />
      </Button>
      <Button variant="outline">
        <Download /> Download dataset
      </Button>
      <Button variant="secondary">
        <Star /> 1,204
      </Button>
    </div>
  );
}

export function States() {
  return (
    <div style={row}>
      <Button>Enabled</Button>
      <Button disabled>Disabled</Button>
      <Button variant="outline" disabled>
        Disabled outline
      </Button>
    </div>
  );
}
