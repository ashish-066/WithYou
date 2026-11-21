'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');

const { findBlockedApps, matchBlockedApp, parsePs, parseTasklist } = require('../src/blocklist');

test('finds blocked apps from macOS paths and Windows names', () => {
  assert.equal(matchBlockedApp('/Applications/zoom.us.app/Contents/MacOS/zoom.us').name, 'Zoom');
  assert.equal(matchBlockedApp('AnyDesk.exe').name, 'AnyDesk');
  assert.equal(matchBlockedApp('/Applications/Slack.app/Contents/Frameworks/Slack Helper').name, 'Slack');
  assert.equal(matchBlockedApp('obs64.exe').name, 'OBS');
});

test('leaves ordinary apps alone', () => {
  for (const command of [
    '/Applications/Safari.app/Contents/MacOS/Safari',
    'zoomwatcher',
    'observer',
    'claudette',
    'teamspeak3.exe',
    'explorer.exe',
    '',
  ]) {
    assert.equal(matchBlockedApp(command), null, command);
  }
});

test('never matches anything in a system folder', () => {
  assert.equal(matchBlockedApp('/System/Library/CoreServices/zoom'), null);
  assert.equal(matchBlockedApp('/usr/bin/slack'), null);
  assert.equal(matchBlockedApp('C:\\Windows\\System32\\teams.exe'), null);
});

test('reads ps output, including paths with spaces', () => {
  const output = '  101 /sbin/launchd\n 2042 /Applications/Microsoft Teams.app/Contents/MacOS/Microsoft Teams\n\nbad\n';
  assert.deepEqual(parsePs(output), [
    { pid: 101, command: '/sbin/launchd' },
    { pid: 2042, command: '/Applications/Microsoft Teams.app/Contents/MacOS/Microsoft Teams' },
  ]);
});

test('reads tasklist output', () => {
  const output = '"System","4","Services","0","148 K"\r\n"Zoom.exe","7788","Console","1","1,024 K"\r\n';
  assert.deepEqual(parseTasklist(output), [
    { pid: 4, command: 'System' },
    { pid: 7788, command: 'Zoom.exe' },
  ]);
});

test('groups processes by app and skips excluded pids', () => {
  const processes = [
    { pid: 1, command: 'Slack' },
    { pid: 2, command: 'Slack Helper' },
    { pid: 3, command: 'discord' },
    { pid: 4, command: 'bash' },
  ];
  assert.deepEqual(findBlockedApps(processes, [3]), [{ name: 'Slack', category: 'Messaging', pids: [1, 2] }]);
});
