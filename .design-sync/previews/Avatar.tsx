import * as React from "react";
import { Avatar, AvatarImage, AvatarFallback } from "paperswithcode";

const row: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 12,
  padding: 20,
};

export function AuthorRow() {
  return (
    <div style={row}>
      <Avatar>
        <AvatarFallback>AV</AvatarFallback>
      </Avatar>
      <Avatar>
        <AvatarFallback>KH</AvatarFallback>
      </Avatar>
      <Avatar>
        <AvatarFallback>YB</AvatarFallback>
      </Avatar>
      <Avatar>
        <AvatarFallback>GH</AvatarFallback>
      </Avatar>
    </div>
  );
}

export function WithImageFallback() {
  return (
    <div style={row}>
      <Avatar>
        <AvatarImage src="https://example.com/vaswani.jpg" alt="Ashish Vaswani" />
        <AvatarFallback>AV</AvatarFallback>
      </Avatar>
      <div style={{ display: "flex", flexDirection: "column" }}>
        <span style={{ fontSize: 14, fontWeight: 500 }}>Ashish Vaswani</span>
        <span style={{ fontSize: 12, color: "hsl(var(--muted-foreground))" }}>
          Lead author · Attention Is All You Need
        </span>
      </div>
    </div>
  );
}
