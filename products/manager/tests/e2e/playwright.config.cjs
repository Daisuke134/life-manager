const { defineConfig, devices } = require('@playwright/test');
module.exports = defineConfig({
  testDir: '.', testMatch: '*.spec.cjs', workers: 1, retries: 0,
  reporter: [['list'], ['json', { outputFile: '../../output/service/browser-results.json' }]],
  use: { baseURL: process.env.MANAGER_BASE_URL || 'http://127.0.0.1:8765/', trace: 'retain-on-failure' },
  projects: [{ name: 'desktop', use: { ...devices['Desktop Chrome'] } }, { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } }],
  webServer: process.env.MANAGER_BASE_URL ? undefined : {
    command: 'python3 -m http.server 8765 --bind 127.0.0.1 --directory ../../output/service/site',
    url: 'http://127.0.0.1:8765/', reuseExistingServer: false,
  },
});
