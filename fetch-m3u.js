const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  // Replace with your proxy details
  // Format: http://username:password@proxy-ip:port
  const proxyServer = 'http://185.112.151.207:8022';

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    proxy: {
      server: proxyServer
    }
  });

  const context = await browser.newContext({
    userAgent:
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    extraHTTPHeaders: {
      'Accept-Language': 'en-US,en;q=0.9'
    }
  });

  const page = await context.newPage();

  await page.goto(
    'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true',
    { waitUntil: 'load', timeout: 120000 }
  );

  await page.waitForSelector('body', { timeout: 120000 });

  const bodyText = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync(path.join(process.cwd(), 'bingcha.m3u'), bodyText);

  console.log('M3U file saved successfully via proxy!');
  await browser.close();
})();
