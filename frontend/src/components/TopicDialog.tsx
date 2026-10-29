import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import TopicSettings from './TopicSettings';

/** The topic editor as a pop-up, so /following shows no input field next to the chat box. */
export default function TopicDialog({ open, onOpenChange, signInToSave = false }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  signInToSave?: boolean;
}) {
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="topic-dialog" aria-describedby={undefined}>
      <DialogTitle className="topic-dialog-title">Follow a topic</DialogTitle>
      <TopicSettings signInToSave={signInToSave} onDone={() => onOpenChange(false)} />
    </DialogContent>
  </Dialog>;
}
