import React from 'react';
import { createRoot } from 'react-dom/client';
import './styles/tokens.css';
import './styles/globals.css';
import { DownloadPage } from './pages/DownloadPage';

// ── Mount React app ────────────────────────────────────────────────────────
const root = document.getElementById('root');
if (!root) throw new Error('Root element #root not found');

createRoot(root).render(
  <React.StrictMode>
    <DownloadPage />
  </React.StrictMode>,
);
