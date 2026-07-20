import * as React from "react";
import { Alert, AlertTitle, AlertDescription } from "paperswithcode";
import { Trophy, AlertCircle } from "lucide-react";

const wrap: React.CSSProperties = { padding: 20, width: 440 };

export function NewResults() {
  return (
    <div style={wrap}>
      <Alert>
        <Trophy />
        <AlertTitle>New state-of-the-art result published</AlertTitle>
        <AlertDescription>
          CoCa reached 91.0% top-1 accuracy on ImageNet, surpassing the previous
          best by 0.3 points.
        </AlertDescription>
      </Alert>
    </div>
  );
}

export function EvaluationFailed() {
  return (
    <div style={wrap}>
      <Alert variant="destructive">
        <AlertCircle />
        <AlertTitle>Evaluation failed</AlertTitle>
        <AlertDescription>
          The submission could not be scored on the WMT14 En-De test set.
          Check that predictions cover all 3,003 examples.
        </AlertDescription>
      </Alert>
    </div>
  );
}
