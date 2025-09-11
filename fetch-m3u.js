const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Navigate to M3U URL
  await page.goto(
    'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true',
    { waitUntil: 'load', timeout: 120000 }
  );

  // Wait for body to render (Cloudflare JS challenge)
  await page.waitForSelector('body', { timeout: 120000 });

  // Extract M3U content from the page
  const bodyText = await page.evaluate(() => document.body.innerText);

  // Save in repo root
  fs.writeFileSync(path.join(process.cwd(), 'bingcha.m3u'), bodyText);
  console.log('M3U file saved successfully!');

  await browser.close();
})();
