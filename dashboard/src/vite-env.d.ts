/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Optional absolute API origin. Omit in dev (Vite proxies `/api` to FastAPI). */
  readonly VITE_API_URL?: string
}
