const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PROXY = 'http://222.252.194.29:8080'; // Replace with your working proxy
const URL = 'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true';
const OUTPUT = path.join(process.cwd(), 'bingcha.m3u');

(async () => {
  try {
    console.log('Launching browser with proxy:', PROXY);

    const browser = await chromium.launch({
      headless: true,
      proxy: { server: PROXY },
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });

    const context = await browser.newContext({
      userAgent:
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      extraHTTPHeaders: { 'Accept-Language': 'en-US,en;q=0.9' },
    });

    const page = await context.newPage();

    console.log('Navigating to M3U URL and waiting for download...');
    await page.goto(URL, { waitUntil: 'networkidle', timeout: 120000 });

    // Wait a few seconds to ensure JS challenge is completed
    await page.waitForTimeout(5000);

    // Extract the content
    const m3uContent = await page.evaluate(() => document.body.innerText);

    if (!m3uContent || !m3uContent.includes('#EXTM3U')) {
      throw new Error('Downloaded content does not look like a valid M3U file.');
    }

    fs.writeFileSync(OUTPUT, m3uContent);
    console.log('M3U file saved successfully at', OUTPUT);

    await browser.close();
  } catch (err) {
    console.error('Error fetching M3U:', err);
    process.exit(1);
  }
})();
