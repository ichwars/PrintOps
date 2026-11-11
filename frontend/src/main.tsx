import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { i18nReady } from './i18n'
import App from './App.tsx'
import { isChunkLoadError, recoverFromMissingChunk } from './utils/lazyPage'

window.addEventListener('vite:preloadError', (event) => {
  const payload = (event as Event & { payload?: Error }).payload
  if (isChunkLoadError(payload)) void recoverFromMissingChunk()
})

const LANGUAGE_WAIT_MS = 3_000

async function mountApp() {
  let timeout: ReturnType<typeof setTimeout> | undefined
  const deadline = new Promise<void>((resolve) => {
    timeout = setTimeout(resolve, LANGUAGE_WAIT_MS)
  })
  try {
    await Promise.race([i18nReady, deadline])
  } catch {
    // English is available locally when loading the preferred language fails.
  } finally {
    clearTimeout(timeout)
  }

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

void mountApp()
