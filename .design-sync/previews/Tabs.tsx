import * as React from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "paperswithcode";

const wrap: React.CSSProperties = { padding: 20 };
const body: React.CSSProperties = { fontSize: 14, lineHeight: 1.5, margin: 0 };

export function PaperTabs() {
  return (
    <div style={wrap}>
      <Tabs defaultValue="overview" style={{ width: 420 }}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="results">Results</TabsTrigger>
          <TabsTrigger value="code">Code</TabsTrigger>
          <TabsTrigger value="bibtex">BibTeX</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <p style={body}>
            The Transformer is the first sequence transduction model based
            entirely on attention, dispensing with recurrence and convolutions
            entirely.
          </p>
        </TabsContent>
        <TabsContent value="results">
          <p style={body}>28.4 BLEU on WMT14 English-to-German.</p>
        </TabsContent>
        <TabsContent value="code">
          <p style={body}>tensorflow/tensor2tensor · 12,400 stars</p>
        </TabsContent>
        <TabsContent value="bibtex">
          <p style={body}>@inproceedings&#123;vaswani2017attention&#125;</p>
        </TabsContent>
      </Tabs>
    </div>
  );
}

export function LeaderboardTabs() {
  return (
    <div style={wrap}>
      <Tabs defaultValue="accuracy" style={{ width: 420 }}>
        <TabsList>
          <TabsTrigger value="accuracy">Top-1 Accuracy</TabsTrigger>
          <TabsTrigger value="params">Parameters</TabsTrigger>
          <TabsTrigger value="flops">FLOPs</TabsTrigger>
        </TabsList>
        <TabsContent value="accuracy">
          <p style={body}>
            CoCa leads ImageNet at 91.0%, followed by Model soups at 90.9%.
          </p>
        </TabsContent>
        <TabsContent value="params">
          <p style={body}>Ranked by model size, from 5M to 2.1B parameters.</p>
        </TabsContent>
        <TabsContent value="flops">
          <p style={body}>Ranked by inference cost in GFLOPs.</p>
        </TabsContent>
      </Tabs>
    </div>
  );
}
