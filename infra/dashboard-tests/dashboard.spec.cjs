// A real browser drives the production Next.js UI and real Compose API/queue/worker/storage.
// No network interception, fabricated results or API substitutes.
const {test, expect} = require('../../runtimes/node_modules/@playwright/test');
const {randomUUID} = require('node:crypto');
const {readFileSync} = require('node:fs');
const {execFileSync} = require('node:child_process');

const successful = `import {test,expect} from '@playwright/test';
test('dashboard real fixture',async({page})=>{
  console.log('dashboard live output smoke');
  await page.goto('http://fixture-app:8080');
  await page.waitForTimeout(10000);
  await expect(page.getByRole('heading',{name:'BrowserGrid Fixture'})).toBeVisible();
  await page.getByRole('button',{name:'Load data'}).click();
  await expect(page.locator('#data')).toHaveText('Network request complete');
});`;

async function newRun(page, code) {
  await page.getByRole('button', {name: 'New run', exact: true}).click();
  const dialog = page.getByRole('dialog', {name: 'Configure a run'});
  await expect(dialog).toBeVisible();
  await dialog.getByLabel('Test code').fill(code);
  const created = page.waitForResponse(response =>
    response.url().endsWith('/api/v1/runs') && response.request().method() === 'POST');
  await dialog.getByRole('button', {name: 'Start browser run'}).click();
  const response = await created;
  expect(response.status()).toBe(201);
  const run = await response.json();
  await expect(dialog).toBeHidden();
  return run.id;
}

async function downloadFromUI(page, context, button) {
  let timeout;
  const downloaded = download => resolveDownload(download);
  const popup = child => child.once('download', downloaded);
  let resolveDownload;
  const received = new Promise((resolve, reject) => {
    resolveDownload = resolve;
    page.once('download', downloaded);
    context.on('page', popup);
    timeout = setTimeout(() => reject(new Error('Artifact download did not start')), 30000);
    button.click().catch(reject);
  });
  try {
    const download = await received;
    expect(await download.failure()).toBeNull();
    const filename = await download.path();
    expect(readFileSync(filename).subarray(0, 8)).toEqual(Buffer.from([137,80,78,71,13,10,26,10]));
  } finally {
    clearTimeout(timeout);
    page.removeListener('download', downloaded);
    context.removeListener('page', popup);
    for (const child of context.pages()) child.removeListener('download', downloaded);
  }
}

test('account, project, live real run, failure evidence, mobile cancellation and tenancy', async ({page, context, browser}, info) => {
  const email = `dashboard-${randomUUID()}@example.test`;
  const password = randomUUID() + '-secure';
  const workspace = `UI workspace ${randomUUID().slice(0, 8)}`;
  const errors = [];
  const streams = [];
  page.on('response', response => {
    if (response.url().endsWith('/events')) streams.push(response);
  });
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await page.getByRole('button', {name: 'New to BrowserGrid? Create an account'}).click();
  await page.getByLabel('Email', {exact: true}).fill(email);
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Create account', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Your testing infrastructure starts here'})).toBeVisible();
  page.once('dialog', dialog => dialog.accept(workspace));
  await page.getByRole('button', {name: 'Create workspace', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Workspace overview'})).toBeVisible();
  page.once('dialog', dialog => dialog.accept('UI fixture project'));
  await page.getByRole('button', {name: 'Create project', exact: true}).click();
  await expect(page.getByRole('button', {name: 'New run', exact: true})).toBeEnabled();

  // Modal keyboard containment, Escape and focus restoration are real UI assertions.
  const trigger = page.getByRole('button', {name: 'New run', exact: true});
  await trigger.click();
  const dialog = page.getByRole('dialog', {name: 'Configure a run'});
  await expect(dialog.getByRole('button', {name: 'Close', exact: true})).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(dialog.getByRole('button', {name: 'Start browser run'})).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(dialog.getByRole('button', {name: 'Close', exact: true})).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();

  const runId = await newRun(page, successful);
  await page.getByRole('button', {name: 'Logs', exact: true}).click();
  await expect(page.getByRole('log', {name: 'Execution events'})).toContainText('dashboard live output smoke');
  await expect(page.locator('.live')).toHaveText('LIVE');
  expect(streams.length).toBeGreaterThan(0);
  const headers = await streams[0].allHeaders();
  expect(headers['cache-control']).toContain('no-transform');
  expect(headers['content-encoding']).toBeUndefined();
  await page.screenshot({path: info.outputPath('live-run.png'), fullPage: true});
  // No page reload or API polling to update UI state: SSE must drive completion.
  await expect(page.getByRole('status', {name: 'Run status'})).toHaveText(/passed/i, {timeout: 90000});
  await page.getByRole('button', {name: /^Tests/}).click();
  await expect(page.locator('.testRow')).toContainText('dashboard real fixture');
  await expect(page.locator('.testRow .badge')).toHaveText(/passed/i);
  await page.screenshot({path: info.outputPath('run-details.png'), fullPage: true});
  await page.getByRole('button', {name: 'Screenshots', exact: true}).click();
  await downloadFromUI(page, context, page.locator('.artifact').first());
  await page.getByRole('button', {name: 'Videos', exact: true}).click();
  await expect(page.locator('.artifact').first()).toContainText('video');
  await page.getByRole('button', {name: 'Traces', exact: true}).click();
  await expect(page.locator('.artifact').first()).toContainText('trace');

  // A separate real session must not see this tenant's execution or artifact.
  const outsider = await browser.newContext({baseURL: process.env.BG_DASHBOARD_URL || 'http://localhost:3000'});
  try {
    const registered = await outsider.request.post('/api/v1/auth/register', {
      data: {email: `outsider-${randomUUID()}@example.test`, password: randomUUID() + '-secure'}
    });
    expect(registered.status()).toBe(201);
    expect((await outsider.request.get(`/api/v1/runs/${runId}`)).status()).toBe(404);
    const artifacts = await (await page.request.get(`/api/v1/runs/${runId}/artifacts`)).json();
    expect(artifacts.length).toBeGreaterThan(0);
    expect((await outsider.request.get(`/api/v1/artifacts/${artifacts[0].id}/download`)).status()).toBe(404);
  } finally { await outsider.close(); }

  await page.getByRole('button', {name: '← All runs'}).click();
  await newRun(page, "import {test,expect} from '@playwright/test';test('dashboard intentional failure',async({page})=>{await page.goto('http://fixture-app:8080');expect('actual').toBe('EXPECTED_UI_FAILURE');});");
  await expect(page.getByRole('status', {name: 'Run status'})).toHaveText(/failed/i, {timeout: 90000});
  await expect(page.locator('.failure')).toContainText('EXPECTED_UI_FAILURE');
  await expect(page.locator('.failure')).not.toContainText('\u001b');
  await expect(page.locator('.testRow')).toHaveAttribute('open', '');
  await page.screenshot({path: info.outputPath('failure-details.png'), fullPage: true});

  await page.getByRole('button', {name: '← All runs'}).click();
  await page.setViewportSize({width: 390, height: 844});
  const cancelledId = await newRun(page, "import {test} from '@playwright/test';test('dashboard cancel running',async({page})=>{await page.waitForTimeout(60000);});");
  await expect(page.locator('.job .badge')).toHaveText(/running/i, {timeout: 60000});
  await page.getByRole('button', {name: 'Cancel run', exact: true}).click();
  await expect(page.getByRole('status', {name: 'Run status'})).toHaveText(/cancelled/i, {timeout: 30000});
  await expect(page.getByText('No test results were produced for this run.', {exact:true})).toBeVisible();
  const cancelled = await (await page.request.get(`/api/v1/runs/${cancelledId}`)).json();
  await expect.poll(() => execFileSync('docker', ['ps','-aq','--filter',`label=browsergrid.job_id=${cancelled.jobs[0].id}`], {encoding:'utf8',timeout:15000}).trim(), {timeout:15000}).toBe('');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: info.outputPath('mobile-cancelled.png'), fullPage: true});

  await page.getByRole('button', {name: 'Open navigation'}).click();
  await page.getByRole('button', {name: 'Sign out', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Welcome back'})).toBeVisible();
  expect((await page.request.get('/api/v1/me')).status()).toBe(401);
  await page.getByLabel('Email', {exact: true}).fill(email);
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Workspace overview'})).toBeVisible();
  await page.getByRole('button', {name: 'Open navigation'}).click();
  await expect(page.getByRole('combobox', {name: 'Workspace'})).toHaveText(workspace);
  expect(errors).toEqual([]);
});
