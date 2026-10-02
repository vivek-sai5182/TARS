// ------------------------------------------------------------
  // electron/main.js
  // ------------------------------------------------------------
  // Entry point for the Electron part of the app.
  // Includes extra console.log statements to help debug the tray.
  // ------------------------------------------------------------

  const { app, BrowserWindow, Tray, Menu, nativeImage } = require('electron');
  const path = require('path');
  const fs = require('fs');

  let mainWindow = null;
  let tray = null;

  /**
   * Helper: log and return a valid NativeImage for the tray.
   * Returns a 16×16 image if the file exists and is readable;
   * otherwise falls back to Electron’s built‑in icon so you can
   * still see *something* in the tray while you fix the asset.
   */
  function loadTrayIcon() {
    const iconPath = path.join(__dirname, 'assets', 'icon.png');
    console.log('[Tray] Looking for icon at:', iconPath);

    if (!fs.existsSync(iconPath)) {
      console.error('[Tray] ❌ File NOT FOUND at', iconPath);
      // Fallback to Electron’s default icon (works on all platforms)
      const fallback = path.join(
        __dirname,
        'node_modules',
        'electron',
        'dist',
        'resources',
        process.platform === 'win32' ? 'default_icon.ico' : 'default_icon.png'
      );
      console.log('[Tray] Using fallback icon:', fallback);
      return nativeImage.createFromPath(fallback).resize({ width: 16, height: 16 });
    }

    const stats = fs.statSync(iconPath);
    console.log('[Tray] ✅ File found – size:', stats.size, 'bytes');
    if (stats.size === 0) {
      console.error('[Tray] ❌ Icon file is empty!');
    }

    // Try to load the image; if it fails we’ll get an empty NativeImage
    const img = nativeImage.createFromPath(iconPath);
    if (img.isEmpty()) {
      console.error('[Tray] ❌ nativeImage.createFromPath returned an empty image – possibly corrupt or unsupported format');
    } else {
      console.log('[Tray] ✅ Loaded icon – dimensions:', img.getSize());
    }

    // Ensure a reasonable size for the tray (16×16 works everywhere)
    return img.resize({ width: 16, height: 16 });
  }

  /**
   * Creates the main BrowserWindow that will host the React app.
   */
  function createWindow() {
    console.log('[App] Creating BrowserWindow …');
    mainWindow = new BrowserWindow({
      width: 1200,
      height: 800,
      icon: path.join(__dirname, 'assets', 'icon.png'),
      show: false, // hide until ready‑to‑show to avoid a white flash
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
      }
    });

    const isDev = !app.isPackaged;

    if (isDev) {
      console.log('[App] Loading development URL: http://localhost:3000');

      mainWindow.loadURL('http://localhost:3000');

      console.log('[App] Opening DevTools …');
      mainWindow.webContents.openDevTools();
    } else {
      console.log('[App] Loading production build');

      mainWindow.loadFile(
        path.join(__dirname, '../build/index.html')
      );
    }

    mainWindow.once('ready-to-show', () => {
      console.log('[App] Window ready – showing');
      mainWindow.show();
    });

    // Hide on close instead of quitting (unless the user chose Quit from tray)
    mainWindow.on('close', (e) => {
      if (!app.isQuitting) {
        console.log('[App] Close intercepted – hiding window');
        e.preventDefault();
        mainWindow.hide();
      }
      return false;
    });
  }

  /**
   * Creates the system‑tray icon and its context menu.
   */
  function createTray() {
    console.log('[Tray] Creating tray …');
    const icon = loadTrayIcon(); // <-- includes all the logging above
    tray = new Tray(icon);
    console.log('[Tray] Tray object created:', !!tray);

    const contextMenu = Menu.buildFromTemplate([
      {
        label: 'Show App',
        click: () => {
          console.log('[Tray] Menu → Show App clicked');
          if (mainWindow) mainWindow.show();
        }
      },
      {
        label: 'Hide App',
        click: () => {
          console.log('[Tray] Menu → Hide App clicked');
          if (mainWindow) mainWindow.hide();
        }
      },
      { type: 'separator' },
      {
        label: 'Settings',
        click: () => {
          console.log('[Tray] Menu → Settings clicked (placeholder)');
          // TODO: replace with real settings UI
        }
      },
      {
        label: 'About',
        click: () => {
          console.log('[Tray] Menu → About clicked (placeholder)');
          // TODO: replace with real about UI
        }
      },
      { type: 'separator' },
      {
        label: 'Quit',
        click: () => {
          console.log('[Tray] Menu → Quit clicked');
          app.isQuitting = true;
          if (mainWindow) mainWindow.destroy();
          app.quit();
        }
      }
    ]);

    console.log('[Tray] Menu built – items:',
      contextMenu.items.map(i => i.label || i.type || '(separator)'));

    tray.setContextMenu(contextMenu);
    console.log('[Tray] Context menu assigned');

    tray.setToolTip('AI Desktop Agent');
    console.log('[Tray] Tooltip set');

    // Optional: left‑click toggles visibility
    tray.on('click', () => {
      console.log('[Tray] Tray clicked');
      if (mainWindow && mainWindow.isVisible()) {
        console.log('[Tray] Hiding window');
        mainWindow.hide();
      } else if (mainWindow) {
        console.log('[Tray] Showing window');
        mainWindow.show();
      }
    });
  }

  /**
   * App lifecycle hooks.
   */
  app.whenReady().then(() => {
    console.log('[App] Electron ready – creating window and tray');
    createWindow();
    createTray();
  });

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
      // On Windows/Linux we keep the app alive via the tray.
      console.log('[App] All windows closed – keeping alive via tray');
    }
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      console.log('[App] activate event – no windows, creating one');
      createWindow();
    }
  });