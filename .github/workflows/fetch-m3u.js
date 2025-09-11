const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  // Launch headless browser
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    extraHTTPHeaders: {
      'Accept-Language': 'en-US,en;q=0.9',
      'Accept-Encoding': 'gzip, deflate, br'
    }
  });

  const page = await context.newPage();

  // Go to the M3U URL (Cloudflare JS challenge will run)
  await page.goto('https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true', {
    waitUntil: 'load',
    timeout: 120000 // 2 minutes in case of slow JS challenge
  });

  // Wait for page body to render
  await page.waitForSelector('body', { timeout: 120000 });

  // Extract M3U content
  const bodyText = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync('bingcha.m3u', bodyText);

  console.log('M3U file saved successfully!');
  await browser.close();
})();
