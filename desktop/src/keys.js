'use strict';

/** Decides what to do with a key press while the interview is locked. */

const EMERGENCY_ACCELERATOR = 'CommandOrControl+Alt+Shift+E';

const BLOCKED_WITH_MODIFIER = new Set(['q', 'w', 'r', 'h', 'm', 'n', 't', 'p', 's', 'o', 'u']);
const BLOCKED_ALONE = new Set(['f5', 'f11', 'f12']);
const CLIPBOARD_KEYS = new Set(['c', 'x', 'v']);

/** Returns 'allow', 'block', or 'clipboard' (block it and report it). */
function classifyKey({ key, control, meta, alt, shift }) {
  const pressed = String(key).toLowerCase();
  const modifier = control || meta;

  if (BLOCKED_ALONE.has(pressed)) return 'block';
  if (alt && pressed === 'f4') return 'block';
  if (!modifier) return 'allow';
  if (shift && (pressed === 'i' || pressed === 'j' || pressed === 'c')) return 'block'; // Developer tools
  if (alt && pressed === 'i') return 'block'; // Developer tools on macOS
  if (CLIPBOARD_KEYS.has(pressed)) return 'clipboard';
  if (BLOCKED_WITH_MODIFIER.has(pressed)) return 'block';
  return 'allow';
}

module.exports = { EMERGENCY_ACCELERATOR, classifyKey };
