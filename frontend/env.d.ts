/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** URL del backend (FastAPI). Por defecto http://localhost:8000 */
  readonly VITE_API_URL?: string
}
