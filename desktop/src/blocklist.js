'use strict';

/**
 * Apps a candidate must close before the interview, and how to find them in a
 * process list. Only apps matched here can ever be closed by the app.
 */

const BLOCKED_APPS = [
  // Remote control
  { name: 'AnyDesk', category: 'Remote control', pattern: /^anydesk\b/ },
  { name: 'TeamViewer', category: 'Remote control', pattern: /^teamviewer\b/ },
  { name: 'RustDesk', category: 'Remote control', pattern: /^rustdesk\b/ },
  { name: 'Parsec', category: 'Remote control', pattern: /^parsec\b/ },
  { name: 'Chrome Remote Desktop', category: 'Remote control', pattern: /^remoting_(host|desktop)\b/ },
  { name: 'VNC', category: 'Remote control', pattern: /^(vncviewer|vncserver|winvnc|tvnserver|realvnc)\b/ },

  // Meetings and screen sharing
  { name: 'Zoom', category: 'Meeting', pattern: /^(zoom\.us|zoom)$/ },
  { name: 'Microsoft Teams', category: 'Meeting', pattern: /^(microsoft teams|ms-teams|teams)\b/ },
  { name: 'Webex', category: 'Meeting', pattern: /^(webex|ciscowebex)/ },
  { name: 'Skype', category: 'Meeting', pattern: /^skype\b/ },

  // Screen recording
  { name: 'OBS', category: 'Screen recording', pattern: /^(obs|obs64|obs32)$/ },
  { name: 'Loom', category: 'Screen recording', pattern: /^loom\b/ },
  { name: 'ScreenFlow', category: 'Screen recording', pattern: /^screenflow\b/ },
  { name: 'Camtasia', category: 'Screen recording', pattern: /^camtasia/ },

  // AI assistants
  { name: 'ChatGPT', category: 'AI assistant', pattern: /^chatgpt\b/ },
  { name: 'Claude', category: 'AI assistant', pattern: /^claude$/ },
  { name: 'Microsoft Copilot', category: 'AI assistant', pattern: /^(microsoft )?copilot\b/ },
  { name: 'Perplexity', category: 'AI assistant', pattern: /^perplexity\b/ },
  { name: 'Cluely', category: 'AI assistant', pattern: /^cluely\b/ },

  // Messaging
  { name: 'Discord', category: 'Messaging', pattern: /^discord\b/ },
  { name: 'Telegram', category: 'Messaging', pattern: /^telegram\b/ },
  { name: 'WhatsApp', category: 'Messaging', pattern: /^whatsapp\b/ },
  { name: 'Slack', category: 'Messaging', pattern: /^slack\b/ },
];

// Nothing under these folders is ever closed, whatever its name
const PROTECTED_PATHS = [/^\/system\//, /^\/usr\/(s?bin|libexec)\//, /^\/sbin\//, /^[a-z]:\\windows\\/];

function processName(command) {
  const parts = command.trim().split(/[\\/]/);
  return parts[parts.length - 1].replace(/\.exe$/i, '').toLowerCase();
}

/** The blocked app a command belongs to, or null. */
function matchBlockedApp(command) {
  const lowered = command.trim().toLowerCase();
  if (!lowered || PROTECTED_PATHS.some((path) => path.test(lowered))) return null;
  const name = processName(lowered);
  return BLOCKED_APPS.find((app) => app.pattern.test(name)) ?? null;
}

/** `ps -axo pid=,comm=` output (macOS and Linux). */
function parsePs(output) {
  const processes = [];
  for (const line of output.split('\n')) {
    const match = line.match(/^\s*(\d+)\s+(.+?)\s*$/);
    if (match) processes.push({ pid: Number(match[1]), command: match[2] });
  }
  return processes;
}

/** `tasklist /fo csv /nh` output (Windows). */
function parseTasklist(output) {
  const processes = [];
  for (const line of output.split(/\r?\n/)) {
    const match = line.match(/^"([^"]+)","(\d+)"/);
    if (match) processes.push({ pid: Number(match[2]), command: match[1] });
  }
  return processes;
}

/**
 * Blocked apps among running processes, one entry per app with all its pids.
 * `excludePids` keeps this app itself out of the list.
 */
function findBlockedApps(processes, excludePids = []) {
  const found = new Map();
  for (const { pid, command } of processes) {
    if (excludePids.includes(pid)) continue;
    const app = matchBlockedApp(command);
    if (!app) continue;
    if (!found.has(app.name)) found.set(app.name, { name: app.name, category: app.category, pids: [] });
    found.get(app.name).pids.push(pid);
  }
  return [...found.values()];
}

module.exports = { BLOCKED_APPS, matchBlockedApp, parsePs, parseTasklist, findBlockedApps };
