// fetch-m3u.js
const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const browser = await chromium.launch({
    headless: false, // visible browser
    slowMo: 50,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();

  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
  await page.setExtraHTTPHeaders({
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br'
  });

  await page.goto('https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true', {
    waitUntil: 'load',
    timeout: 90000
  });

  await page.waitForSelector('body', { timeout: 90000 });
  const bodyText = await page.evaluate(() => document.body.innerText);

  fs.writeFileSync('bingcha.m3u', bodyText);
  await browser.close();
})();
