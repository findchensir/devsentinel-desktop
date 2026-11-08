import { app, BrowserWindow } from 'electron';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

let mainWindow: BrowserWindow | null = null;
const currentDirectory = dirname(fileURLToPath(import.meta.url));

app.whenReady().then(() => {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    title: 'DevSentinel Desktop',
    webPreferences: {
      nodeIntegration: true,  // 允许在渲染进程中使用 Node.js API
      contextIsolation: false, // 禁用上下文隔离，以便在渲染进程中直接访问 Node.js API
    },
  });

  const devServerUrl =
    process.env.VITE_DEV_SERVER_URL ??
    (!app.isPackaged ? 'http://localhost:5173' : undefined);

  if (devServerUrl) {
    // 开发模式下加载 Vite 服务，以支持热更新。
    mainWindow.loadURL(devServerUrl);
  } else {
    // 打包后加载构建完成的前端页面。
    mainWindow.loadFile(join(currentDirectory, '../dist/index.html'));
  }

  // 打开开发者工具
  mainWindow.webContents.openDevTools();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});