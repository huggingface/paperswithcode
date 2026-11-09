import type { ReactElement } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { isNotFound } from "@/lib/apiTransport";
import NotFound from "@/pages/NotFound";

/**
 * What a page shows in place of its content when a request it needs failed:
 * the not-found page if any of them was a 404, otherwise `message` as an
 * error. Null when none of `errors` is set.
 */
export function loadFailurePage(errors: unknown[], message: string): ReactElement | null {
  if (errors.some(isNotFound)) return <NotFound />;
  if (!errors.some(Boolean)) return null;
  return (
    <div className="page">
      <Alert variant="destructive">
        <AlertDescription>{message}</AlertDescription>
      </Alert>
    </div>
  );
}
