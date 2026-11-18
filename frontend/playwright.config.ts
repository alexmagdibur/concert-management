import { defineConfig } from '@playwright/test'

const baseURL = process.env.E2E_BASE_URL
const port = baseURL ? new URL(baseURL).port : '5173'

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  timeout: 60_000,
  use: {
    baseURL,
    channel: process.env.E2E_BROWSER || undefined,
  },
  webServer: baseURL ? {
    command: `npm run dev -- --port ${port}`,
    url: baseURL,
    reuseExistingServer: false,
  } : undefined,
})
