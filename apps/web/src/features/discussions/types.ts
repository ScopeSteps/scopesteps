import type { components } from '@scopesteps/api-client';

type Schemas = components['schemas'];
export type Thread = Schemas['ThreadResponse'];
export type Comment = Schemas['CommentResponse'];
export type ThreadCounts = Schemas['ThreadCountsResponse'];
export type MemberMatch = Schemas['MemberMatchResponse'];
export type Participant = Schemas['ParticipantResponse'];

/** What a discussion panel shows: one item's threads, or the whole project's. */
export type DiscussionScope = { kind: 'item'; itemId: string; title: string } | { kind: 'project' };

export type ThreadFilter = 'open' | 'resolved' | 'all';

/** What a thread is about, as its card names it. */
export function aboutLabel(thread: Thread): string {
  if (!thread.item) {
    return 'General discussion';
  }
  const kind = thread.item.kind === 'epic' ? 'Epic' : 'Story';
  return `${kind} · ${thread.item.title}`;
}

/** What someone did in the thread, in plain words: "Wrote · Following". */
export function participation(person: Participant): string {
  return [person.wrote && 'Wrote', person.mentioned && 'Mentioned', person.following && 'Following']
    .filter(Boolean)
    .join(' · ');
}
