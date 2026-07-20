import * as React from "react";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableCaption,
  Badge,
} from "paperswithcode";

const rows = [
  { rank: 1, model: "CoCa (finetuned)", top1: "91.0%", extra: "Yes", params: "2.1B" },
  { rank: 2, model: "Model soups (BASIC-L)", top1: "90.9%", extra: "Yes", params: "2.4B" },
  { rank: 3, model: "ViT-G/14", top1: "90.5%", extra: "Yes", params: "1.8B" },
  { rank: 4, model: "CvT-W24", top1: "87.7%", extra: "No", params: "277M" },
];

export function Leaderboard() {
  return (
    <div style={{ padding: 20 }}>
      <Table>
        <TableCaption>ImageNet — Image Classification leaderboard</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Rank</TableHead>
            <TableHead>Model</TableHead>
            <TableHead>Top-1 Acc.</TableHead>
            <TableHead>Extra Data</TableHead>
            <TableHead>Params</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.rank}>
              <TableCell style={{ fontWeight: 600 }}>{r.rank}</TableCell>
              <TableCell>{r.model}</TableCell>
              <TableCell>{r.top1}</TableCell>
              <TableCell>
                <Badge variant={r.extra === "Yes" ? "secondary" : "outline"}>{r.extra}</Badge>
              </TableCell>
              <TableCell>{r.params}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
