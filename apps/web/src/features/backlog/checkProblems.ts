import type { BacklogVersion, Check } from './types';

type ProblemRef = Check['refs'][number];

const CRITERION_CHARS = 60;

/** At most `max` characters, cut at a word boundary. */
function shorten(text: string, max: number): string {
  if (text.length <= max) {
    return text;
  }
  const cut = text.slice(0, max - 1);
  const space = cut.lastIndexOf(' ');
  return `${(space > 0 ? cut.slice(0, space) : cut).replace(/[\s,.;:]+$/, '')}…`;
}

/**
 * A server problem as people see it: the story and criterion or the decision it is about, looked
 * up in the version on screen. The server's wording, which names ids, is kept only when the ref
 * names nothing this version holds.
 */
export function describeProblem(
  problem: string,
  ref: ProblemRef | undefined,
  version: BacklogVersion,
): string {
  if (ref?.decision_id) {
    const decision = version.decisions.find((d) => d.id === ref.decision_id);
    if (decision) {
      return decision.status === 'skipped'
        ? `Decision “${decision.subject}” was skipped and still needs an answer`
        : `Decision “${decision.subject}” is still open`;
    }
  }
  const item = ref?.item_id ? version.items.find((i) => i.id === ref.item_id) : undefined;
  if (item) {
    const criterion = item.criteria.find((c) => c.id === ref?.criterion_id);
    return criterion
      ? `Agent suggestion “${shorten(criterion.text, CRITERION_CHARS)}” on ${item.kind} “${item.title}” is not reviewed yet`
      : `${item.kind === 'epic' ? 'Epic' : 'Story'} “${item.title}”: ${problem}`;
  }
  return problem;
}
