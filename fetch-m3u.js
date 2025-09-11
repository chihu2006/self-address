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

    // Catch the response
    let m3uContent = '';
    page.on('response', async (response) => {
      const url = response.url();
      if (url.includes('fy.188766.xyz')) { // target M3U URL
        try {
          m3uContent = await response.text();
        } catch (err) {
          console.warn('Failed to read response text:', err);
        }
      }
    });

    console.log('Navigating to M3U URL...');
    await page.goto(
      'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true',
      { waitUntil: 'domcontentloaded', timeout: 120000 }
    );

    if (!m3uContent) {
      throw new Error('M3U content not captured from response');
    }

    const filePath = path.join(process.cwd(), 'bingcha.m3u');
    fs.writeFileSync(filePath, m3uContent);
    console.log('M3U file saved successfully at', filePath);

    await browser.close();
  } catch (err) {
    console.error('Error fetching M3U:', err);
    process.exit(1);
  }
})();
