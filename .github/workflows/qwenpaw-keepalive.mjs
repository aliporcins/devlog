// QwenPaw keep-alive: log in to AgentScope Platform and open the app.
// Runs in GitHub Actions (Playwright). The password comes from the
// AGENTSCOPE_PASSWORD repo secret; never log it.
import { chromium } from 'playwright';

const APP_URL = 'https://01a20de6-a388-7cc3-9596-ef0ef7ac0088.qwenpaw.platform.agentscope.io/';
const LOGIN_URL = 'https://platform.agentscope.io/login';
const EMAIL = 'aliporcins@gmail.com';
const password = process.env.AGENTSCOPE_PASSWORD;

if (!password) {
  console.error('AGENTSCOPE_PASSWORD secret is not set');
  process.exit(1);
}

const browser = await chromium.launch();
const page = await browser.newPage();
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

  // 2. Open the QwenPaw app and confirm the chat UI actually loads
  // (not just the loading screen, and not the expired-link page).
  await page.goto(APP_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  try {
    await page.waitForFunction(() => {
      return location.pathname.includes('/chat') || document.body.innerText.includes('Default');
    }, null, { timeout: 90000 });
  } catch {
    const text = (await page.evaluate(() => document.body.innerText)).slice(0, 500);
    if (text.includes('访问链接已失效')) throw new Error('App returned the expired-link page');
    throw new Error('Chat UI did not load within 90s; page text: ' + JSON.stringify(text));
  }
  console.log('App URL:', page.url());
  console.log('QwenPaw keep-alive OK');
} catch (err) {
  console.error('Keep-alive failed:', err.message);
  try { console.error('Failed at URL:', page.url()); } catch {}
  process.exit(1);
} finally {
  await browser.close();
}
