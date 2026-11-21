'use strict';

/**
 * Remembers on disk that an interview is locked. If this file still says
 * "locked" when the app starts, the last run ended without a submit: force
 * quit, crash, power loss. The app then reports it and resumes the interview.
 */

const fs = require('node:fs');

// Nobody can stay locked in forever, even if everything else goes wrong
const MAX_LOCK_MS = 4 * 60 * 60 * 1000;

class LockState {
  constructor(filePath) {
    this.filePath = filePath;
  }

  read() {
    try {
      const data = JSON.parse(fs.readFileSync(this.filePath, 'utf8'));
      return data && data.locked === true ? data : null;
    } catch {
      return null;
    }
  }

  write({ token, lockedAt }) {
    fs.writeFileSync(this.filePath, JSON.stringify({ locked: true, token: token ?? null, lockedAt }), {
      mode: 0o600,
    });
  }

  clear() {
    fs.rmSync(this.filePath, { force: true });
  }
}

function lockExpired(lockedAt, now = Date.now()) {
  return now - lockedAt >= MAX_LOCK_MS;
}

/**
 * Lets the same violation through only once per cooldown, so a window that
 * keeps losing focus doesn't flood the recruiter's timeline.
 */
class Cooldown {
  constructor(ms, now = () => Date.now()) {
    this.ms = ms;
    this.now = now;
    this.last = new Map();
  }

  allow(key) {
    const previous = this.last.get(key);
    if (previous !== undefined && this.now() - previous < this.ms) return false;
    this.last.set(key, this.now());
    return true;
  }
}

module.exports = { LockState, Cooldown, lockExpired, MAX_LOCK_MS };
