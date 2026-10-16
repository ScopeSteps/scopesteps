import { statSync } from 'node:fs';

import { BaseSequencer } from 'vitest/node';
import type { TestSpecification } from 'vitest/node';

/**
 * Splits test files across `--shard` runs by size instead of by path hash, so each CI shard gets
 * a similar amount of work: a file's size tracks how long it runs closely enough. Every shard
 * computes the same split from the same files, largest first into the lightest shard.
 */
export class BalancedSequencer extends BaseSequencer {
  override shard(files: TestSpecification[]): Promise<TestSpecification[]> {
    const { shard } = this.ctx.config;
    if (!shard) {
      return Promise.resolve(files);
    }
    const sized = files
      .map((spec) => ({ spec, size: statSync(spec.moduleId).size }))
      .sort((a, b) => b.size - a.size || a.spec.moduleId.localeCompare(b.spec.moduleId));
    const shards = Array.from({ length: shard.count }, () => ({
      size: 0,
      specs: [] as TestSpecification[],
    }));
    for (const { spec, size } of sized) {
      const lightest = shards.reduce((least, next) => (next.size < least.size ? next : least));
      lightest.size += size;
      lightest.specs.push(spec);
    }
    return Promise.resolve(shards[shard.index - 1]?.specs ?? []);
  }
}
