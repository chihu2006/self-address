const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const proxifly = require('proxifly');

(async () => {
  try {
    // Get a free proxy from Proxifly
    const proxy = await proxifly.getProxy({ protocol: 'http' }); 
    console.log('Using proxy:', proxy);

    const browser = await chromium.launch({
      headless: true,
      proxy: { server: `http://${proxy}` },
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const context = await browser.newContext({
      userAgent:
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      extraHTTPHeaders: { 'Accept-Language': 'en-US,en;q=0.9' }
    });

    const page = await context.newPage();

    // Navigate to M3U page
    await page.goto(
      'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true',
      { waitUntil: 'load', timeout: 120000 }
    );

    // Extract M3U content
    const bodyText = await page.evaluate(() => document.body.innerText);

    // Save in repo root
    const filePath = path.join(process.cwd(), 'bingcha.m3u');
    fs.writeFileSync(filePath, bodyText);

    console.log('M3U file saved successfully!');
    await browser.close();
  } catch (err) {
    console.error('Error fetching M3U:', err);
    process.exit(1);
  }
})();
