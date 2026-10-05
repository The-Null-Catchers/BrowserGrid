const { test, expect } = require('@browsergrid/test');
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');

test('pinned public Git checkout', async ({ page }, testInfo) => {
  const input = JSON.parse(fs.readFileSync('/work/input.json', 'utf8'));
  const commit = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  expect(commit).toBe(input.config.source.commit.toLowerCase());
  expect(testInfo.config.metadata.acceptance).toBe('pinned-git-fixture');
  expect(page.viewportSize()).toEqual({ width: 1024, height: 768 });
  await testInfo.attach('checkout.json', {
    body: Buffer.from(JSON.stringify({ commit, fixture: 'pinned-git-fixture' })),
    contentType: 'application/json'
  });
  await page.goto('http://fixture-app:8080');
  await expect(page.getByRole('heading', { name: 'BrowserGrid Fixture' })).toBeVisible();
  await page.evaluate(() => console.log('browsergrid capture smoke'));
  await page.getByRole('button', { name: 'Load data' }).click();
  await expect(page.locator('#data')).toHaveText('Network request complete');
});
