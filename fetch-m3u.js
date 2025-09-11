const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  try {
    console.log('Launching browser with proxy...');
    const browser = await chromium.launch({
      headless: true,
      proxy: { server: 'http://222.252.194.29:8080' }, // optional proxy
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const context = await browser.newContext({
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      extraHTTPHeaders: { 'Accept-Language': 'en-US,en;q=0.9' }
    });

    const page = await context.newPage();

    const M3U_URL = 'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true';
    const filePath = path.join(process.cwd(), 'bingcha.m3u');

    // Intercept the request and fetch response
    await page.route(M3U_URL, async (route) => {
      const response = await route.fetch();
      const body = await response.text();
      fs.writeFileSync(filePath, body);
      console.log('M3U file saved successfully at', filePath);
      await browser.close();
    });

    console.log('Navigating to M3U URL...');
    await page.goto(M3U_URL, { waitUntil: 'networkidle', timeout: 120000 });

  } catch (err) {
    console.error('Error fetching M3U:', err);
    process.exit(1);
  }
})();
