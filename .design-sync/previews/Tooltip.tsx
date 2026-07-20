import * as React from "react";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
  Button,
} from "paperswithcode";

export function Default() {
  return (
    <div style={{ padding: 40, display: "flex", justifyContent: "center" }}>
      <TooltipProvider>
        <Tooltip open>
          <TooltipTrigger asChild>
            <Button variant="outline">Reproducibility</Button>
          </TooltipTrigger>
          <TooltipContent>
            Results verified against the official implementation
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}
