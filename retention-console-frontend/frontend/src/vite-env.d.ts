/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string
  readonly VITE_USE_MSW?: string
}
interface ImportMeta {
  readonly env: ImportMetaEnv
}
