import { Capacitor } from '@capacitor/core';
import type { DownloadEngine } from './DownloadEngine';
import { DesktopDownloadEngine } from './DesktopDownloadEngine';
import { AndroidDownloadEngine } from './AndroidDownloadEngine';

let currentEngine: DownloadEngine | null = null;

export function getDownloadEngine(): DownloadEngine {
  if (!currentEngine) {
    if (Capacitor.isNativePlatform()) {
      currentEngine = new AndroidDownloadEngine();
    } else {
      currentEngine = new DesktopDownloadEngine();
    }
  }
  return currentEngine;
}

export function setDownloadEngine(engine: DownloadEngine | null): void {
  currentEngine = engine;
}
