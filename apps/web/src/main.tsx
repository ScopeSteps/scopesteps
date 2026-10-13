import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import '@fontsource/figtree/latin-400.css';
import '@fontsource/figtree/latin-500.css';
import '@fontsource/figtree/latin-600.css';
import '@fontsource/figtree/latin-700.css';
import '@fontsource/figtree/latin-ext-400.css';
import '@fontsource/figtree/latin-ext-500.css';
import '@fontsource/figtree/latin-ext-600.css';
import '@fontsource/figtree/latin-ext-700.css';
import '@fontsource/ibm-plex-mono/latin-400.css';
import '@fontsource/ibm-plex-mono/latin-500.css';
import '@fontsource/ibm-plex-mono/latin-ext-400.css';
import '@fontsource/ibm-plex-mono/latin-ext-500.css';

import { App } from '@/app/App';
import '@/index.css';
import { applyAppearance, loadPreferences } from '@/lib/preferences';

// Before the first render, so a stored dark theme never flashes light.
applyAppearance(loadPreferences());

const root = document.getElementById('root');
if (!root) {
  throw new Error('Root element #root not found');
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
