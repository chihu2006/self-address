const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const PROXY = 'http://222.252.194.29:8080';
  const URL = 'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true';
  const OUTPUT = path.join(process.cwd(), 'bingcha.m3u');

  try {
    console.log('Launching browser with proxy:', PROXY);
    const browser = await chromium.launch({
      headless: true,
      proxy: { server: PROXY },
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const context = await browser.newContext({
      userAgent:
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      extraHTTPHeaders: { 'Accept-Language': 'en-US,en;q=0.9' }
    });

    const page = await context.newPage();

    console.log('Navigating to M3U URL and waiting for download...');
    const [download] = await Promise.all([
      page.waitForEvent('download'), // wait for the download event
      page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 120000 }) // trigger download
    ]);

    await download.saveAs(OUTPUT);
    console.log('M3U file downloaded successfully at', OUTPUT);

    await browser.close();
  } catch (err) {
    console.error('Error fetching M3U:', err);
    process.exit(1);
  }
})();
