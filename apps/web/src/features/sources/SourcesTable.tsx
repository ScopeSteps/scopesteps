import { Link } from 'react-router';

import { Tag } from '@/components/Tag';

import { formatAddedAt, plural } from './format';
import { KIND_LABELS } from './types';
import type { SourceVersion } from './types';

interface SourcesTableProps {
  versions: SourceVersion[];
}

export function SourcesTable({ versions }: SourcesTableProps) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full min-w-[34rem] border-collapse text-sm">
        <caption className="sr-only">Stored sources</caption>
        <thead>
          <tr>
            {['Source', 'Type', 'Size', 'Added'].map((column) => (
              <th
                key={column}
                scope="col"
                className="border-b border-line bg-surface-2 px-3.5 py-2.5 text-left text-xs font-semibold text-subtle"
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {versions.map((version) => (
            <tr key={version.id} className="border-b border-line last:border-b-0">
              <td className="px-3.5 py-3 align-top">
                <span className="flex items-center gap-2">
                  <Tag tone="accent" className="font-mono tabular-nums">
                    v{version.version}
                  </Tag>
                  <Link
                    to={{ search: `?version=${version.id}` }}
                    className="font-semibold [overflow-wrap:anywhere] text-fg hover:text-accent-ink hover:underline"
                  >
                    {version.filename}
                  </Link>
                </span>
              </td>
              <td className="px-3.5 py-3 align-top">{KIND_LABELS[version.kind]}</td>
              <td className="px-3.5 py-3 align-top font-mono text-[13px] whitespace-nowrap tabular-nums">
                {plural(version.block_count, '¶', '¶')} · {plural(version.word_count, 'word')}
              </td>
              <td className="px-3.5 py-3 align-top text-xs whitespace-nowrap text-subtle">
                <time dateTime={version.created_at}>{formatAddedAt(version.created_at)}</time>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
