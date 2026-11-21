'use strict';

/** Lists running apps and closes blocked ones. */

const { execFile } = require('node:child_process');
const { findBlockedApps, parsePs, parseTasklist } = require('./blocklist');

function run(command, args) {
  return new Promise((resolve, reject) => {
    execFile(command, args, { maxBuffer: 16 * 1024 * 1024, windowsHide: true }, (error, stdout) => {
      if (error) reject(error);
      else resolve(stdout);
    });
  });
}

// Replaceable in tests
const system = {
  platform: process.platform,
  run,
  kill: (pid, signal) => process.kill(pid, signal),
  wait: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
};

async function listProcesses() {
  if (system.platform === 'win32') {
    return parseTasklist(await system.run('tasklist', ['/fo', 'csv', '/nh']));
  }
  return parsePs(await system.run('ps', ['-axo', 'pid=,comm=']));
}

// Set only in development runs, e.g. so testing doesn't close the tools in use
let ignoredApps = [];

function setIgnoredApps(names) {
  ignoredApps = names;
}

async function scanBlockedApps() {
  const blocked = findBlockedApps(await listProcesses(), [process.pid, process.ppid]);
  return blocked.filter((app) => !ignoredApps.includes(app.name));
}

/** The command that asks (or, with force, makes) one process close. */
function closeCommand(pid, force) {
  if (system.platform === 'win32') {
    // Without /F Windows only asks the window to close, and chat and meeting
    // apps (Teams, Slack, Discord, WhatsApp, Zoom) just hide in the system tray.
    // /T also ends the helper processes they start.
    return force ? ['taskkill', ['/F', '/T', '/PID', String(pid)]] : ['taskkill', ['/PID', String(pid)]];
  }
  return null;
}

/**
 * Closes whatever blocked apps are running right now and returns those still
 * open. Takes no list from the page, so the page can't name other processes.
 *
 * Without `force` it only asks them to close. With `force` (the candidate
 * agreed after seeing which apps are still running) it ends them.
 */
async function closeBlockedApps({ force = false } = {}) {
  for (const app of await scanBlockedApps()) {
    for (const pid of app.pids) {
      try {
        const command = closeCommand(pid, force);
        if (command) await system.run(...command);
        else system.kill(pid, force ? 'SIGKILL' : 'SIGTERM');
      } catch {
        // Already gone (e.g. ended with its parent), or not ours: the next scan reports it
      }
    }
  }
  await system.wait(1500);
  return scanBlockedApps();
}

module.exports = { scanBlockedApps, closeBlockedApps, setIgnoredApps, system };
