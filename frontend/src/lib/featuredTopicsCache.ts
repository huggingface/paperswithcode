import type { TopicBubble } from '@/lib/api/research';

const KEY = 'pwc:featured-topics';

/** The popular topics this browser last saw, so the homepage cards paint before the request returns. */
export function readFeaturedTopics(): { at: number; topics: TopicBubble[] } | undefined {
  try {
    const cached = JSON.parse(localStorage.getItem(KEY) ?? 'null');
    return Array.isArray(cached?.topics) && typeof cached.at === 'number' ? cached : undefined;
  } catch {
    return undefined;
  }
}

export function writeFeaturedTopics(topics: TopicBubble[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ at: Date.now(), topics }));
  } catch {
    // Without storage the cards wait for the request, as on a first visit.
  }
}
