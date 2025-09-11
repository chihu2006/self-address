// fetch-m3u.js
const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const browser = await chromium.launch({
    headless: true, // required on GitHub Actions
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();

  // Set realistic User-Agent
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

  // Extra headers for anti-bot
  await page.setExtraHTTPHeaders({
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br'
  });

  // Navigate with long timeout
  await page.goto('https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true', {
    waitUntil: 'load',
    timeout: 90000
  });

  // Wait for page to render (Cloudflare JS challenge)
  await page.waitForSelector('body', { timeout: 90000 });

  // Get the M3U content
  const bodyText = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync('bingcha.m3u', bodyText);

  await browser.close();
})();
