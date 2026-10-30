import { Button } from '@/components/Button';
import { roleLabelOf } from '@/features/identity';

import type { MyWork, SummaryRole } from './myWork';

interface RoleSummaryProps {
  roles: MyWork['roles'];
  selected: SummaryRole | null;
  onSelect: (role: SummaryRole | null) => void;
}

/** "Product owner on 2 · Business analyst on 3": each role held is a toggle that filters. */
export function RoleSummary({ roles, selected, onSelect }: RoleSummaryProps) {
  const held = roles.filter((total) => total.projects > 0);
  if (held.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div role="group" aria-label="Filter projects by role" className="flex flex-wrap gap-2">
        {held.map((total) => {
          const pressed = total.role === selected;
          return (
            <Button
              key={total.role}
              size="sm"
              variant={pressed ? 'soft' : 'default'}
              aria-pressed={pressed}
              onClick={() => {
                onSelect(pressed ? null : total.role);
              }}
            >
              {roleLabelOf(total.role)} on{' '}
              <span className="font-mono tabular-nums">{total.projects}</span>
              {total.waiting > 0 && (
                <>
                  {' '}
                  <span className="text-muted">
                    · <span className="font-mono tabular-nums">{total.waiting}</span> waiting
                  </span>
                </>
              )}
            </Button>
          );
        })}
      </div>
      {selected !== null && (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            onSelect(null);
          }}
        >
          Clear filter
        </Button>
      )}
    </div>
  );
}
