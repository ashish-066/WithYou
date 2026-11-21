'use strict';

/**
 * Presence View desktop app: shows the interview page in a locked window.
 *
 * While locked, normal ways of leaving are blocked, and whatever can't be
 * blocked (force quit, power loss, switching away) is reported to the recruiter.
 * The emergency shortcut always works, so nobody can be trapped.
 */

const path = require('node:path');
const {
  app,
  BrowserWindow,
  Menu,
  clipboard,
  dialog,
  globalShortcut,
  ipcMain,
  powerMonitor,
  screen,
  session,
  shell,
  systemPreferences,
} = require('electron');

const { closeBlockedApps, scanBlockedApps, setIgnoredApps } = require('./processes');
const { EMERGENCY_ACCELERATOR, classifyKey } = require('./keys');
const { LockState, Cooldown, lockExpired, MAX_LOCK_MS } = require('./lock-state');
const { inviteFromArgv, inviteFromLink, interviewUrl, isAllowedUrl } = require('./links');
const config = require('../app-config.json');

// Development overrides never apply to a packaged app
const APP_URL = (!app.isPackaged && process.env.PRESENCE_APP_URL) || config.appUrl;
const DEV_NO_KIOSK = !app.isPackaged && process.env.PRESENCE_DEV_NO_KIOSK === '1';

if (!app.isPackaged && process.env.PRESENCE_DEV_IGNORE_APPS) {
  setIgnoredApps(process.env.PRESENCE_DEV_IGNORE_APPS.split(','));
}

const MONITOR_INTERVAL_MS = 5000;
const RELOAD_DELAY_MS = 5000;

let win = null;
let lockState = null;
let inviteToken = inviteFromArgv(process.argv);
let locked = false;
let lockedAt = 0;
let allowQuit = false;
let showingDialog = false;
let rendererReady = false;
let monitorTimer = null;
let lockTimer = null;

const pendingViolations = [];
const cooldown = new Cooldown(60 * 1000);
const focusCooldown = new Cooldown(15 * 1000);

// =============================================================================
// Reporting
// =============================================================================

function report(flagType, severity, description) {
  const violation = { flag_type: flagType, severity, description };
  if (win && !win.isDestroyed() && rendererReady) win.webContents.send('desktop:violation', violation);
  else pendingViolations.push(violation);
}

// =============================================================================
// Lock
// =============================================================================

function applyWindowLock(on) {
  if (!win || win.isDestroyed()) return;
  win.setContentProtection(on);
  win.setClosable(!on);
  win.setMinimizable(!on);
  if (DEV_NO_KIOSK) return;
  win.setAlwaysOnTop(on, 'screen-saver');
  win.setKiosk(on);
}

async function checkEnvironment() {
  try {
    for (const blocked of await scanBlockedApps()) {
      if (cooldown.allow(`app:${blocked.name}`)) {
        report('blocked_app', 'high', `${blocked.name} (${blocked.category}) was open during the interview`);
      }
    }
  } catch {
    // A failed scan isn't evidence of anything: try again next time
  }
  const displays = screen.getAllDisplays().length;
  if (displays > 1 && cooldown.allow('second_screen')) {
    report('second_screen', 'high', `${displays} screens were connected during the interview`);
  }
}

function lock(token, startedAt = Date.now()) {
  inviteToken = token ?? inviteToken;
  if (locked) {
    lockState.write({ token: inviteToken, lockedAt });
    return;
  }
  locked = true;
  lockedAt = startedAt;
  lockState.write({ token: inviteToken, lockedAt });
  applyWindowLock(true);
  clipboard.clear();
  globalShortcut.register(EMERGENCY_ACCELERATOR, confirmEmergencyExit);
  monitorTimer = setInterval(checkEnvironment, MONITOR_INTERVAL_MS);
  void checkEnvironment();
  lockTimer = setTimeout(
    () => {
      report('lock_expired', 'low', 'The app unlocked itself after reaching its time limit');
      unlock();
    },
    Math.max(0, MAX_LOCK_MS - (Date.now() - lockedAt)),
  );
}

function unlock() {
  locked = false;
  lockState.clear();
  clearInterval(monitorTimer);
  clearTimeout(lockTimer);
  globalShortcut.unregister(EMERGENCY_ACCELERATOR);
  applyWindowLock(false);
}

async function confirmEmergencyExit() {
  if (!locked || showingDialog || !win) return;
  showingDialog = true;
  try {
    const { response } = await dialog.showMessageBox(win, {
      type: 'warning',
      buttons: ['Go back to the interview', 'Unlock the app'],
      defaultId: 0,
      cancelId: 0,
      title: 'Emergency exit',
      message: 'Unlock the app?',
      detail:
        'Use this only for a real emergency or if the app has stopped working. ' +
        'Your recruiter will see that you used it.',
    });
    if (response === 1 && locked) {
      report('emergency_exit', 'high', 'The candidate used the emergency exit');
      unlock();
    }
  } finally {
    showingDialog = false;
  }
}

// =============================================================================
// Window
// =============================================================================

function guardWindow(contents) {
  contents.setWindowOpenHandler(({ url }) => {
    // Links away from the app open in the normal browser, and only when unlocked
    if (!locked && url.startsWith('https://')) void shell.openExternal(url);
    return { action: 'deny' };
  });

  contents.on('will-navigate', (event, url) => {
    if (!isAllowedUrl(url, APP_URL)) event.preventDefault();
  });

  contents.on('before-input-event', (event, input) => {
    if (!locked || input.type !== 'keyDown') return;
    const action = classifyKey(input);
    if (action === 'allow') return;
    event.preventDefault();
    if (action === 'clipboard' && cooldown.allow('clipboard')) {
      report('copy_paste', 'medium', 'The candidate tried to copy or paste during the interview');
    }
  });

  contents.on('did-fail-load', (_event, code, _description, url, isMainFrame) => {
    // -3 means the load was replaced by another one, not that it failed
    if (!isMainFrame || code === -3 || url.startsWith('file:')) return;
    void contents.loadFile(path.join(__dirname, 'offline.html'));
    setTimeout(() => {
      if (!contents.isDestroyed()) void contents.loadURL(interviewUrl(APP_URL, inviteToken));
    }, RELOAD_DELAY_MS);
  });

  contents.on('render-process-gone', () => {
    rendererReady = false;
    if (locked) report('app_closed', 'medium', 'The interview page crashed and was reloaded');
    if (!contents.isDestroyed()) contents.reload();
  });
}

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 700,
    backgroundColor: '#0a0b0e',
    title: 'Presence View',
    // Window and taskbar icon (Windows, Linux); the Mac app uses its bundle icon
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      devTools: !app.isPackaged,
    },
  });

  guardWindow(win.webContents);

  win.on('close', (event) => {
    if (locked && !allowQuit) {
      event.preventDefault();
      if (cooldown.allow('exit_attempt')) report('exit_attempt', 'low', 'The candidate tried to close the app');
    }
  });

  win.on('blur', () => {
    if (!locked || showingDialog) return;
    if (focusCooldown.allow('focus')) {
      report('tab_switch', 'medium', 'The candidate left the interview window');
    }
    if (!DEV_NO_KIOSK) {
      win.moveTop();
      win.focus();
    }
  });

  win.on('closed', () => {
    win = null;
    rendererReady = false;
  });

  void win.loadURL(interviewUrl(APP_URL, inviteToken));
}

function openInvite(token) {
  // A running interview can't be swapped for another one
  if (!token || locked) return;
  inviteToken = token;
  if (win) void win.loadURL(interviewUrl(APP_URL, token));
}

// =============================================================================
// Messages from the interview page
// =============================================================================

function handle(channel, handler) {
  ipcMain.handle(channel, (event, ...args) => {
    const frameUrl = event.senderFrame?.url ?? '';
    if (!isAllowedUrl(frameUrl, APP_URL)) throw new Error('Not allowed');
    return handler(...args);
  });
}

function registerHandlers() {
  handle('desktop:status', async () => ({
    version: app.getVersion(),
    locked,
    displays: screen.getAllDisplays().length,
    blockedApps: (await scanBlockedApps()).map(({ name, category }) => ({ name, category })),
  }));

  // force: the candidate saw which apps are still running and agreed to end them
  handle('desktop:close-blocked-apps', async (options) =>
    (await closeBlockedApps({ force: options?.force === true })).map(({ name, category }) => ({ name, category })),
  );

  handle('desktop:request-media', async () => {
    if (process.platform === 'darwin') {
      const camera = await systemPreferences.askForMediaAccess('camera');
      const microphone = await systemPreferences.askForMediaAccess('microphone');
      return camera && microphone;
    }
    if (process.platform === 'win32') {
      // Windows can't prompt; a "denied" here means camera or microphone access
      // is off in Settings > Privacy (for all apps or for desktop apps)
      const denied = ['camera', 'microphone'].some((kind) => systemPreferences.getMediaAccessStatus(kind) === 'denied');
      return !denied;
    }
    return true;
  });

  handle('desktop:lock', (token) => {
    lock(typeof token === 'string' ? token : null);
  });

  handle('desktop:unlock', () => {
    if (locked) unlock();
  });

  handle('desktop:ready', () => {
    rendererReady = true;
    const queued = pendingViolations.splice(0);
    return queued;
  });
}

function restrictPermissions() {
  const allowed = (permission, url) => permission === 'media' && isAllowedUrl(url, APP_URL);
  session.defaultSession.setPermissionRequestHandler((_contents, permission, callback, details) => {
    callback(allowed(permission, details.requestingUrl));
  });
  session.defaultSession.setPermissionCheckHandler((_contents, permission, origin) => allowed(permission, origin));
}

/** Tells our own server the request comes from this app. Other sites never see it. */
function identifyToServer() {
  session.defaultSession.webRequest.onBeforeSendHeaders((details, callback) => {
    if (!isAllowedUrl(details.url, APP_URL)) {
      callback({ requestHeaders: details.requestHeaders });
      return;
    }
    callback({ requestHeaders: { ...details.requestHeaders, 'X-Presence-Desktop': app.getVersion() } });
  });
}

// =============================================================================
// App lifecycle
// =============================================================================

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', (_event, argv) => {
    openInvite(inviteFromArgv(argv));
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });

  app.on('open-url', (event, link) => {
    event.preventDefault();
    const token = inviteFromLink(link);
    if (app.isReady()) openInvite(token);
    else inviteToken = token ?? inviteToken;
  });

  app.on('before-quit', (event) => {
    if (locked && !allowQuit) {
      event.preventDefault();
      if (cooldown.allow('exit_attempt')) report('exit_attempt', 'low', 'The candidate tried to close the app');
    }
  });

  // Windows shutting down or logging off: never hold up the computer. The next
  // start finds the lock still on disk and reports it.
  app.on('session-end', () => {
    allowQuit = true;
  });

  app.on('window-all-closed', () => {
    app.quit();
  });

  app.on('will-quit', () => {
    globalShortcut.unregisterAll();
  });

  // A development run shouldn't take over presenceview:// links on this computer
  if (app.isPackaged) app.setAsDefaultProtocolClient('presenceview');

  void app.whenReady().then(() => {
    Menu.setApplicationMenu(null);
    // A development run (npm start) uses Electron's own bundle and icon; the
    // installed app gets its icon from build/icon.icns
    if (process.platform === 'darwin' && !app.isPackaged) app.dock?.setIcon(path.join(__dirname, 'icon.png'));
    lockState = new LockState(path.join(app.getPath('userData'), 'interview-lock.json'));
    restrictPermissions();
    identifyToServer();
    registerHandlers();

    powerMonitor.on('shutdown', () => {
      allowQuit = true;
    });

    const previous = lockState.read();
    if (previous && lockExpired(previous.lockedAt)) {
      lockState.clear();
    } else if (previous) {
      inviteToken = inviteToken ?? previous.token;
      report('app_closed', 'high', 'The app closed before the interview was submitted and was reopened');
    }

    createWindow();
    if (previous && !lockExpired(previous.lockedAt)) lock(previous.token, previous.lockedAt);

    screen.on('display-added', () => {
      if (locked) void checkEnvironment();
    });
  });
}
