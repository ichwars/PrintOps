import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './i18n' // Initialize i18n
import App from './App.tsx'

window.addEventListener('vite:preloadError', (event) => {
  event.preventDefault()
  const payload = (event as Event & { payload?: Error }).payload
  const reloadKey = `printops:chunk-reload:${payload?.message ?? 'unknown'}`

  if (sessionStorage.getItem(reloadKey)) return

  sessionStorage.setItem(reloadKey, '1')
  window.location.reload()
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
