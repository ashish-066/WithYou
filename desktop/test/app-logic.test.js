'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');

const { classifyKey } = require('../src/keys');
const { inviteFromArgv, inviteFromLink, interviewUrl, isAllowedUrl } = require('../src/links');
const { Cooldown, LockState, MAX_LOCK_MS, lockExpired } = require('../src/lock-state');

const key = (pressed, modifiers = {}) => ({ key: pressed, control: false, meta: false, alt: false, shift: false, ...modifiers });

test('blocks quitting, reloading and developer tools', () => {
  assert.equal(classifyKey(key('q', { meta: true })), 'block');
  assert.equal(classifyKey(key('w', { control: true })), 'block');
  assert.equal(classifyKey(key('F4', { alt: true })), 'block');
  assert.equal(classifyKey(key('F5')), 'block');
  assert.equal(classifyKey(key('F12')), 'block');
  assert.equal(classifyKey(key('i', { meta: true, alt: true })), 'block');
  assert.equal(classifyKey(key('I', { control: true, shift: true })), 'block');
});

test('reports copy and paste', () => {
  assert.equal(classifyKey(key('v', { meta: true })), 'clipboard');
  assert.equal(classifyKey(key('C', { control: true })), 'clipboard');
  assert.equal(classifyKey(key('x', { control: true })), 'clipboard');
});

test('lets normal typing and editing through', () => {
  assert.equal(classifyKey(key('q')), 'allow');
  assert.equal(classifyKey(key('V', { shift: true })), 'allow');
  assert.equal(classifyKey(key('z', { meta: true })), 'allow');
  assert.equal(classifyKey(key('a', { control: true })), 'allow');
  assert.equal(classifyKey(key('Enter')), 'allow');
});

test('reads invite tokens only from valid links', () => {
  const token = 'aaa-1.bbb_2.ccc3';
  assert.equal(inviteFromLink(`presenceview://interview?invite=${token}`), token);
  assert.equal(inviteFromLink(`https://interview?invite=${token}`), null);
  assert.equal(inviteFromLink(`presenceview://other?invite=${token}`), null);
  assert.equal(inviteFromLink('presenceview://interview?invite=../../etc'), null);
  assert.equal(inviteFromLink('presenceview://interview?invite=no-dots'), null);
  assert.equal(inviteFromLink(`presenceview://interview?invite=a.b.${'c'.repeat(2000)}`), null);
  assert.equal(inviteFromLink('presenceview://interview'), null);
  assert.equal(inviteFromLink('not a link'), null);
  assert.equal(inviteFromArgv(['app', '--flag', `presenceview://interview?invite=${token}`]), token);
  assert.equal(inviteFromArgv(['app', '--flag']), null);
});

test('only allows pages from the configured app', () => {
  const appUrl = 'https://app.example.com';
  assert.equal(isAllowedUrl('https://app.example.com/interview', appUrl), true);
  assert.equal(isAllowedUrl('https://app.example.com.evil.test/', appUrl), false);
  assert.equal(isAllowedUrl('http://app.example.com/', appUrl), false);
  assert.equal(isAllowedUrl('file:///etc/passwd', appUrl), false);
  assert.equal(isAllowedUrl('nonsense', appUrl), false);
});

test('builds the interview address', () => {
  assert.equal(interviewUrl('https://app.example.com', 'a.b.c'), 'https://app.example.com/interview?invite=a.b.c');
  assert.equal(interviewUrl('https://app.example.com', null), 'https://app.example.com/interview');
});

test('a lock left on disk survives a restart until it is cleared', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'presence-lock-'));
  try {
    const state = new LockState(path.join(dir, 'lock.json'));
    assert.equal(state.read(), null);
    state.write({ token: 'abc12345', lockedAt: 1000 });
    assert.deepEqual(new LockState(state.filePath).read(), { locked: true, token: 'abc12345', lockedAt: 1000 });
    state.clear();
    assert.equal(state.read(), null);
    fs.writeFileSync(state.filePath, 'not json');
    assert.equal(state.read(), null);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('a lock can never outlast its time limit', () => {
  assert.equal(lockExpired(0, MAX_LOCK_MS - 1), false);
  assert.equal(lockExpired(0, MAX_LOCK_MS), true);
});

test('repeated violations are reported once per cooldown', () => {
  let now = 0;
  const cooldown = new Cooldown(100, () => now);
  assert.equal(cooldown.allow('a'), true);
  assert.equal(cooldown.allow('a'), false);
  assert.equal(cooldown.allow('b'), true);
  now = 100;
  assert.equal(cooldown.allow('a'), true);
});
