#!/usr/bin/env node
/**
 * Design rules for the frontend (context/dashboard_rebuild_plan.md, section 2.1).
 * Runs before every build; exits 1 and lists each violation.
 *
 * Everywhere in src/ (except the legacy files below):
 *   - no gradients: CSS *-gradient(), Tailwind bg-gradient-*, SVG <linearGradient>/<radialGradient>
 *
 * In the new UI (src/ui, src/lib, src/areas, src/features):
 *   - no emoji (icons come from lucide-react)
 *   - no default fonts (Inter, Roboto, Arial, system-ui, -apple-system); fonts come from src/ui/tokens.css
 *   - no 3+ column grids (the "row of equal cards" layout); use tables, lists or a main + side column
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const src = join(root, 'src');

// Files allowed to carry gradients. Empty since the rebuild finished; keep it that way.
const LEGACY_GRADIENTS = new Set([]);

const NEW_UI_DIRS = ['src/ui/', 'src/lib/', 'src/areas/', 'src/features/'];

const GRADIENT = /(?:repeating-)?(?:linear|radial|conic)-gradient\s*\(|\bbg-gradient-|<(?:linear|radial)Gradient\b/i;
const EMOJI = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}]/u;
const DEFAULT_FONT = /(?:font-family\s*:|fontFamily)[^;\n]*\b(?:Inter|Roboto|Arial|Helvetica|system-ui|-apple-system|BlinkMacSystemFont|Segoe UI)\b|\bfont-(?:sans|serif)\b/;
const WIDE_GRID = /\b(?:[a-z0-9[\]:-]+:)?grid-cols-(?:[3-9]|1[0-2])\b/;

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) out.push(...walk(path));
    else if (/\.(tsx?|css|html)$/.test(name)) out.push(path);
  }
  return out;
}

const problems = [];
const legacySeen = new Set();

for (const file of walk(src)) {
  const rel = relative(root, file).split(sep).join('/');
  const isNew = NEW_UI_DIRS.some((d) => rel.startsWith(d));
  const lines = readFileSync(file, 'utf8').split('\n');

  lines.forEach((line, i) => {
    const at = `${rel}:${i + 1}`;
    if (GRADIENT.test(line)) {
      if (LEGACY_GRADIENTS.has(rel)) legacySeen.add(rel);
      else problems.push(`${at}  gradient: ${line.trim()}`);
    }
    if (!isNew) return;
    if (EMOJI.test(line)) problems.push(`${at}  emoji (use a lucide-react icon or a word): ${line.trim()}`);
    if (DEFAULT_FONT.test(line)) problems.push(`${at}  default font (use font-display / font-ui / font-mono): ${line.trim()}`);
    if (WIDE_GRID.test(line)) problems.push(`${at}  3+ column grid (use a table, a list or main + side column): ${line.trim()}`);
  });
}

// A legacy file that lost its gradient should leave the list, so it can't come back
for (const rel of LEGACY_GRADIENTS) {
  if (!legacySeen.has(rel)) problems.push(`${rel}  no longer uses a gradient (or is gone): remove it from LEGACY_GRADIENTS in scripts/check-ui-rules.mjs`);
}

if (problems.length) {
  console.error(`UI rules: ${problems.length} problem(s)\n`);
  for (const p of problems) console.error(`  ${p}`);
  console.error('\nRules: context/dashboard_rebuild_plan.md, section 2.1');
  process.exit(1);
}
console.log(`UI rules: ok (${LEGACY_GRADIENTS.size} legacy file(s) with gradients left to rebuild)`);
