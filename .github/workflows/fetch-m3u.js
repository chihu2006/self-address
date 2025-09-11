// fetch-m3u.js
const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();

  // Navigate to the URL
  await page.goto('https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true', { waitUntil: 'networkidle' });

  // Get the content
  const bodyText = await page.evaluate(() => document.body.innerText);

  // Save to file
  fs.writeFileSync('bingcha.m3u', bodyText);

  await browser.close();
})();
