import * as React from "react";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  SelectGroup,
  SelectLabel,
  Label,
} from "paperswithcode";

export function FilterControls() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, padding: 20, width: 280 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <Label>Task</Label>
        <Select defaultValue="cls">
          <SelectTrigger>
            <SelectValue placeholder="Select a task" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectLabel>Computer Vision</SelectLabel>
              <SelectItem value="cls">Image Classification</SelectItem>
              <SelectItem value="seg">Semantic Segmentation</SelectItem>
              <SelectItem value="det">Object Detection</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <Label>Sort by</Label>
        <Select defaultValue="acc">
          <SelectTrigger>
            <SelectValue placeholder="Sort results" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="acc">Accuracy</SelectItem>
            <SelectItem value="date">Publication date</SelectItem>
            <SelectItem value="stars">GitHub stars</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
