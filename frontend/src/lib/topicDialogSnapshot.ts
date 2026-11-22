import type { ResearchTopic } from '@/lib/api/research';
import type { FollowPick } from '@/lib/researchTopic';

/** The feed pop-up as it was when a link in it opened another page: Back to that page reopens it like this. */
export interface TopicDialogSnapshot {
  topicId: number | null;
  editId: number | null;
  draft: string | null;
  selection: FollowPick[];
  removals: number[];
  topicFollows: number[];
  order: ResearchTopic[] | null;
  privacy: Record<number, boolean>;
  tab: string;
  scrollTop: number;
}

const PREFIX = 'pwc:topic-dialog:';

/** Kept per history entry, so only Back (or Forward) to the page the pop-up was on reopens it. */
export function saveTopicDialog(entry: string, snapshot: TopicDialogSnapshot) {
  try {
    sessionStorage.setItem(PREFIX + entry, JSON.stringify(snapshot));
  } catch {
    return;
  }
}

export function readTopicDialog(entry: string): TopicDialogSnapshot | null {
  try {
    const raw = sessionStorage.getItem(PREFIX + entry);
    return raw ? JSON.parse(raw) as TopicDialogSnapshot : null;
  } catch {
    return null;
  }
}

export function clearTopicDialog(entry: string) {
  try {
    sessionStorage.removeItem(PREFIX + entry);
  } catch {
    return;
  }
}
