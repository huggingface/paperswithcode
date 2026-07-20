import * as React from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  Button,
  Badge,
} from "paperswithcode";

const pad: React.CSSProperties = { padding: 20, maxWidth: 420 };

export function PaperCard() {
  return (
    <div style={pad}>
      <Card>
        <CardHeader>
          <CardTitle>Attention Is All You Need</CardTitle>
          <CardDescription>
            Vaswani et al. — NeurIPS 2017
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p style={{ fontSize: 14, lineHeight: 1.5, margin: 0 }}>
            The dominant sequence transduction models are based on complex
            recurrent or convolutional neural networks. We propose a new simple
            network architecture, the Transformer, based solely on attention
            mechanisms.
          </p>
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <Badge variant="secondary">Machine Translation</Badge>
            <Badge variant="outline">Transformers</Badge>
          </div>
        </CardContent>
        <CardFooter style={{ gap: 8 }}>
          <Button size="sm">Get code</Button>
          <Button size="sm" variant="outline">
            Read paper
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}

export function StatCard() {
  return (
    <div style={pad}>
      <Card>
        <CardHeader>
          <CardDescription>State-of-the-art on ImageNet</CardDescription>
          <CardTitle style={{ fontSize: 32 }}>91.1%</CardTitle>
        </CardHeader>
        <CardContent>
          <p style={{ fontSize: 13, color: "hsl(var(--muted-foreground))", margin: 0 }}>
            Top-1 accuracy · CoCa (finetuned) · +0.3% over previous best
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
