import { useState } from "react";
import { Share2 } from "lucide-react";

import { ChatShareDialog } from "./ChatDialogs";
import { Spinner } from "./icons";
import { useToast } from "@/hooks/use-toast";
import { chatApi } from "@/lib/api/chat";

interface ChatSharingProps {
  sessionId: string;
  busy: boolean;
  loading: boolean;
  hasPaperSelection?: boolean;
  onError: (message: string) => void;
}

export function ChatSharing({
  sessionId,
  busy,
  loading,
  hasPaperSelection = false,
  onError,
}: ChatSharingProps) {
  const { toast } = useToast();
  const [pending, setPending] = useState(false);
  const [manualUrl, setManualUrl] = useState("");

  const share = async () => {
    if (busy || pending) return;
    if (hasPaperSelection && !window.confirm(
      "This public link will include the selected paper passage. Anyone with the link can read that passage. Continue?",
    )) return;
    setPending(true);
    try {
      const result = await chatApi.createOrRefreshShare(sessionId);
      const url = new URL(result.public_path, window.location.origin).toString();
      try {
        if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
        await navigator.clipboard.writeText(url);
        toast({
          className: "chat-share-toast",
          duration: 5_000,
          title: "Public link copied to your clipboard",
          description: "Anyone with this link can see this conversation.",
        });
      } catch {
        setManualUrl(url);
      }
    } catch (error) {
      const message = error instanceof Error
        ? error.message
        : "Could not share this conversation";
      onError(message);
      toast({ variant: "destructive", title: "Share failed", description: message });
    } finally {
      setPending(false);
    }
  };

  return <>
    <button
      type="button"
      className="chat-share-button"
      onClick={() => void share()}
      disabled={busy || pending || loading}
      aria-label="Share conversation"
    >
      {pending ? <Spinner /> : <Share2 aria-hidden="true" />}
      <span>Share</span>
    </button>
    <ChatShareDialog url={manualUrl} onClose={() => setManualUrl("")} />
  </>;
}
