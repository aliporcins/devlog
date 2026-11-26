// QwenPaw keep-alive: log in to AgentScope Platform, open the app through the
// deploy page's "Open QWENPAW" button, and confirm the chat UI loads.
// A bare visit to the app URL returns the expired-link page even when logged
// in (verified 2026-11-26 in a GitHub runner) — the button click is what
// activates the link, exactly like opening it from the deploy page by hand.
// Runs in GitHub Actions (Playwright). Password from AGENTSCOPE_PASSWORD.
import { chromium } from 'playwright';

const LOGIN_URL = 'https://platform.agentscope.io/login';
const DEPLOY_URL = 'https://platform.agentscope.io/deploy';
const EMAIL = 'aliporcins@gmail.com';
const password = process.env.AGENTSCOPE_PASSWORD;

if (!password) {
  console.error('AGENTSCOPE_PASSWORD secret is not set');
  process.exit(1);
}

const browser = await chromium.launch();
const context = await browser.newContext();
const page = await context.newPage();
try {
  // 1. Log in to the platform (the login page is a React SPA).
  await page.goto(LOGIN_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('input[type="password"]', { timeout: 60000 });
  const emailInput = page.locator('input[type="email"]').first();
  if (await emailInput.count()) {
    await emailInput.fill(EMAIL);
  } else {
    await page.locator('input[type="text"], input:not([type])').first().fill(EMAIL);
  }
  await page.locator('input[type="password"]').first().fill(password);
  const submit = page.locator('button[type="submit"]').first();
  if (await submit.count()) {
    await submit.click();
  } else {
    const signIn = page.locator('button:has-text("Sign in"), button:has-text("Log in"), button:has-text("登录")').first();
    if (await signIn.count()) {
      await signIn.click();
    } else {
      await page.locator('input[type="password"]').first().press('Enter');
    }
  }
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 60000 });
  console.log('Logged in to AgentScope Platform');

  // 2. Open the app through the deploy page's Open button.
  await page.goto(DEPLOY_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('text=Open QWENPAW', { timeout: 60000 });
  const pagesBefore = context.pages().length;
  await page.getByText('Open QWENPAW').first().click();
  // The button opens the app in a new tab (or navigates this tab).
  let target = page;
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    const pages = context.pages();
    if (pages.length > pagesBefore) { target = pages[pages.length - 1]; break; }
    if (!page.url().includes('/deploy')) break;
    await page.waitForTimeout(1000);
  }
  console.log('App page URL:', target.url());

  // 3. Confirm the chat UI actually loads (not the loading screen,
  // and not the expired-link page).
  try {
    await target.waitForFunction(() => {
      return location.pathname.includes('/chat') || document.body.innerText.includes('Default');
    }, null, { timeout: 90000 });
  } catch {
    const text = (await target.evaluate(() => document.body.innerText)).slice(0, 500);
    if (text.includes('访问链接已失效')) throw new Error('App returned the expired-link page');
    throw new Error('Chat UI did not load within 90s; page text: ' + JSON.stringify(text));
  }
  console.log('App URL:', target.url());
  console.log('QwenPaw keep-alive OK');
} catch (err) {
  console.error('Keep-alive failed:', err.message);
  try { console.error('Failed at URL:', page.url()); } catch {}
  process.exit(1);
} finally {
  await browser.close();
}
