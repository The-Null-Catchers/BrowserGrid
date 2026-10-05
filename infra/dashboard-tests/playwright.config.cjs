const { defineConfig } = require('../../runtimes/node_modules/@playwright/test');

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: '*.spec.cjs',
  timeout: 240000,
  expect: { timeout: 15000 },
  workers: 1,
  retries: 0,
  outputDir: '../../dashboard-evidence/results',
  reporter: [['list'], ['html', { outputFolder: '../../dashboard-evidence/report', open: 'never' }]],
  use: {
    baseURL: process.env.BG_DASHBOARD_URL || 'http://localhost:3000',
    browserName: 'chromium',
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure'
  }
});
