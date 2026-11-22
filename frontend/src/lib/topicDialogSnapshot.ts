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

const KEY = 'pwcTopicDialog';

/** Kept in the current history entry's state, so only Back (or Forward, or a reload) to that very entry reopens
 * the pop-up; a fresh visit to the same page is a new entry without it. */
export function saveTopicDialog(snapshot: TopicDialogSnapshot) {
  window.history.replaceState({ ...window.history.state, [KEY]: snapshot }, '');
}

export function readTopicDialog(): TopicDialogSnapshot | null {
  return window.history.state?.[KEY] ?? null;
}

export function clearTopicDialog() {
  if (!window.history.state?.[KEY]) return;
  const state = { ...window.history.state };
  delete state[KEY];
  window.history.replaceState(state, '');
}
