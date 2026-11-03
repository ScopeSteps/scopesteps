import ts from 'typescript';
import { describe, expect, it } from 'vitest';

// The words people read, kept to the glossary in docs/product/glossary.md: "approved version"
// and "proposed version", never the internal "baseline" or "candidate".
const INTERNAL = /\b(baselines?|candidates?)\b/i;

const sources = import.meta.glob<string>(
  ['./**/*.{ts,tsx}', '!./**/*.test.{ts,tsx}', '!./test/**'],
  {
    query: '?raw',
    import: 'default',
    eager: true,
  },
);

/**
 * Text a person can read: JSX text and quoted strings that are prose. A string with a space, or
 * one that starts with a capital ("Candidate"), is prose; a bare lower-case token is an API value,
 * class name or path ("baseline", "items-baseline", "./candidate").
 */
function isProse(text: string): boolean {
  return /\s/.test(text.trim()) || /^[A-Z]/.test(text);
}

function readableTexts(path: string, source: string): string[] {
  const file = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const found: string[] = [];
  const visit = (node: ts.Node) => {
    // Module paths and style class names ("items-baseline") are code, not text.
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
      return;
    }
    if (ts.isJsxAttribute(node) && node.name.getText(file) === 'className') {
      return;
    }
    if (ts.isCallExpression(node) && node.expression.getText(file) === 'cx') {
      return;
    }
    if (ts.isJsxText(node)) {
      found.push(node.text);
    } else if (
      ts.isStringLiteral(node) ||
      ts.isNoSubstitutionTemplateLiteral(node) ||
      ts.isTemplateHead(node) ||
      ts.isTemplateMiddle(node) ||
      ts.isTemplateTail(node)
    ) {
      if (isProse(node.text)) {
        found.push(node.text);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return found;
}

describe('plain words', () => {
  it('reads the source files it checks', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(50);
  });

  it('finds the words in text people read and nowhere else', () => {
    const sample = [
      "import { isCandidate } from './candidate';",
      'const title = `Candidate v${String(2)}`;',
      'const Note = () => <p className="items-baseline">The current baseline stays.</p>;',
      "const state = status === 'baseline';",
    ].join('\n');

    const flagged = readableTexts('sample.tsx', sample).filter((text) => INTERNAL.test(text));

    expect(flagged).toEqual(['Candidate v', 'The current baseline stays.']);
  });

  it('never shows "baseline" or "candidate"; the app says approved and proposed version', () => {
    const offending = Object.entries(sources).flatMap(([path, source]) =>
      readableTexts(path, source)
        .filter((text) => INTERNAL.test(text))
        .map((text) => `${path}: ${text.trim()}`),
    );

    expect(offending).toEqual([]);
  });
});
