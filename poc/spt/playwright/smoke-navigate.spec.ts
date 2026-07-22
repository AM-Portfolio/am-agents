import { test, expect } from '@playwright/test';

const targetUrl = process.env.POC_TARGET_URL || 'https://httpbin.org/get';

test('smoke navigate', async ({ page }) => {
  await page.goto(targetUrl);
  await expect(page).toHaveURL(/httpbin/);
});
