'use strict';

const assert = require('node:assert/strict');
const { test, beforeEach } = require('node:test');

const processes = require('../src/processes');

let calls;
let running;

function fakeSystem(platform) {
  calls = [];
  Object.assign(processes.system, {
    platform,
    wait: async () => {},
    kill: (pid, signal) => {
      calls.push(['kill', pid, signal]);
      if (signal === 'SIGKILL' || platform === 'darwin') running = running.filter((p) => p.pid !== pid);
    },
    run: async (command, args) => {
      if (command === 'tasklist') return running.map((p) => `"${p.name}.exe","${p.pid}","Console","1","100 K"`).join('\r\n');
      if (command === 'ps') return running.map((p) => `${p.pid} /Applications/${p.name}`).join('\n');
      calls.push([command, ...args]);
      const pid = Number(args[args.length - 1]);
      // Windows: a polite close only hides tray apps; /F ends them
      if (args.includes('/F')) running = running.filter((p) => p.pid !== pid);
      return '';
    },
  });
}

beforeEach(() => {
  running = [
    { name: 'Slack', pid: 101 },
    { name: 'Notepad', pid: 102 },
  ];
});

test('Windows: a polite close leaves tray apps running, force ends them', async () => {
  fakeSystem('win32');
  const remaining = await processes.closeBlockedApps();
  assert.deepEqual(calls, [['taskkill', '/PID', '101']]);
  assert.deepEqual(remaining.map((a) => a.name), ['Slack']);

  const after = await processes.closeBlockedApps({ force: true });
  assert.deepEqual(calls.at(-1), ['taskkill', '/F', '/T', '/PID', '101']);
  assert.deepEqual(after, []);
  assert.ok(running.some((p) => p.name === 'Notepad'), 'apps not on the blocklist are never touched');
});

test('Mac: asks with SIGTERM, and only forces when told to', async () => {
  fakeSystem('darwin');
  assert.deepEqual(await processes.closeBlockedApps(), []);
  assert.deepEqual(calls, [['kill', 101, 'SIGTERM']]);
});
