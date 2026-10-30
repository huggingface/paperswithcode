import React, { useCallback, useEffect, useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { useToast } from "@/hooks/use-toast";
import { copyNodeAsPng } from "@/lib/copyScreenshot";

interface CopyScreenshotButtonProps {
  /** Node to capture. Lazily resolved on click so the button stays usable
   *  even if the ref is attached after a render-skipping branch. */
  targetRef: React.RefObject<HTMLElement>;
  /** Surface name used in the failure toast (e.g. "leaderboard"). */
  label: string;
}

const CopyScreenshotButton: React.FC<CopyScreenshotButtonProps> = ({ targetRef, label }) => {
  const { toast } = useToast();
  const [status, setStatus] = useState<"idle" | "copying" | "copied">("idle");
  const resetTimer = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (resetTimer.current !== null) {
        window.clearTimeout(resetTimer.current);
      }
    };
  }, []);

  const handleClick = useCallback(async () => {
    const node = targetRef.current;
    if (!node) return;
    setStatus("copying");
    node.classList.add("is-capturing");
    // Force the browser to flush the style/layout change that reveals the
    // screenshot-only title, then wait one paint frame so html-to-image's
    // clone walk sees the post-toggle dimensions. Without this, the title
    // is missing on tall cards like the leaderboard table.
    void node.offsetHeight;
    await new Promise<void>((resolve) =>
      window.requestAnimationFrame(() => resolve()),
    );
    try {
      await copyNodeAsPng(node);
      setStatus("copied");
      toast({
        title: "Screenshot copied",
        description: `Image of the ${label} copied to your clipboard.`,
      });
      if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
      resetTimer.current = window.setTimeout(() => setStatus("idle"), 1500);
    } catch (err) {
      setStatus("idle");
      toast({
        title: "Copy failed",
        description:
          err instanceof Error && err.message
            ? err.message
            : "Could not copy the screenshot to your clipboard.",
        variant: "destructive",
      });
    } finally {
      node.classList.remove("is-capturing");
    }
  }, [targetRef, label, toast]);

  const text = status === "copied" ? "Copied" : status === "copying" ? "Copying…" : "Copy image";

  return (
    <button
      type="button"
      className="bm-copy-btn"
      onClick={handleClick}
      disabled={status === "copying"}
      aria-label={`Copy ${label} screenshot to clipboard`}
      title={`Copy ${label} screenshot to clipboard`}
    >
      <Icon name="copy" size={11} />
      {text}
    </button>
  );
};
export default CopyScreenshotButton;
