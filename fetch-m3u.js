const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  try {
    console.log('Using fixed proxy: 222.252.194.29:8080');

    const browser = await chromium.launch({
      headless: true,
      proxy: { server: 'http://222.252.194.29:8080' },
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const context = await browser.newContext({
      userAgent:
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      extraHTTPHeaders: { 'Accept-Language': 'en-US,en;q=0.9' }
    });

    const page = await context.newPage();

    // Listen for downloads
    page.on('download', async (download) => {
      const filePath = path.join(process.cwd(), 'bingcha.m3u');
      await download.saveAs(filePath);
      console.log('M3U file downloaded successfully at', filePath);
    });

    console.log('Navigating to M3U URL...');
    // This triggers the download
    await page.goto(
      'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true',
      { waitUntil: 'load', timeout: 120000 }
    );

    // Wait a few seconds to ensure download event fires
    await page.waitForTimeout(5000);

    await browser.close();
  } catch (err) {
    console.error('Error fetching M3U:', err);
    process.exit(1);
  }
})();
