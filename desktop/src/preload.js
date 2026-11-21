'use strict';

/** The only desktop features the interview page can reach. */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('presenceDesktop', {
  status: () => ipcRenderer.invoke('desktop:status'),
  /** Asks blocked apps to close; with { force: true }, ends them (after the candidate agreed). */
  closeBlockedApps: (options) => ipcRenderer.invoke('desktop:close-blocked-apps', { force: options?.force === true }),
  requestMedia: () => ipcRenderer.invoke('desktop:request-media'),
  lock: (inviteToken) => ipcRenderer.invoke('desktop:lock', inviteToken),
  unlock: () => ipcRenderer.invoke('desktop:unlock'),

  /** Calls back with each violation, starting with any recorded before the page loaded. */
  onViolation: (callback) => {
    const listener = (_event, violation) => callback(violation);
    ipcRenderer.on('desktop:violation', listener);
    void ipcRenderer.invoke('desktop:ready').then((queued) => queued.forEach(callback));
    return () => ipcRenderer.removeListener('desktop:violation', listener);
  },
});
