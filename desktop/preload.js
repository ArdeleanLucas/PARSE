'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('parseDesktop', {
  ping: () => ipcRenderer.invoke('parse-desktop:ping'),
  getConfig: () => ipcRenderer.invoke('parse-desktop:get-config'),
});
