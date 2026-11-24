import type { PopularFollow, TopicBubble } from '@/lib/api/research';

const TOPICS_KEY = 'pwc:featured-topics';
const FOLLOWS_KEY = 'pwc:popular-follows';

function read<T>(key: string, field: string): { at: number; items: T[] } | undefined {
  try {
    const cached = JSON.parse(localStorage.getItem(key) ?? 'null');
    return Array.isArray(cached?.[field]) && typeof cached.at === 'number' ? { at: cached.at, items: cached[field] } : undefined;
  } catch {
    return undefined;
  }
}

function write(key: string, field: string, items: unknown[]): void {
  try {
    localStorage.setItem(key, JSON.stringify({ at: Date.now(), [field]: items }));
  } catch {
    // Without storage the cards wait for the request, as on a first visit.
  }
}

/** The popular topics this browser last saw, so the homepage cards paint before the request returns. */
export function readFeaturedTopics(): { at: number; topics: TopicBubble[] } | undefined {
  const cached = read<TopicBubble>(TOPICS_KEY, 'topics');
  return cached && { at: cached.at, topics: cached.items };
}

export function writeFeaturedTopics(topics: TopicBubble[]): void {
  write(TOPICS_KEY, 'topics', topics);
}

/** The most followed tasks and methods this browser last saw, for the same homepage cards. */
export function readPopularFollows(): { at: number; follows: PopularFollow[] } | undefined {
  const cached = read<PopularFollow>(FOLLOWS_KEY, 'follows');
  return cached && { at: cached.at, follows: cached.items };
}

export function writePopularFollows(follows: PopularFollow[]): void {
  write(FOLLOWS_KEY, 'follows', follows);
}
