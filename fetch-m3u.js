const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  try {
    console.log('Launching browser with proxy: http://222.252.194.29:8080');

    const browser = await chromium.launch({
      headless: true,
      proxy: { server: 'http://222.252.194.29:8080' },
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });

    const context = await browser.newContext();

    const M3U_URL = 'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true';
    const filePath = path.join(process.cwd(), 'bingcha.m3u');

    console.log('Fetching M3U via API request...');
    const response = await context.request.get(M3U_URL, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
      },
    });

    if (!response.ok()) {
      throw new Error(`Failed to fetch M3U: ${response.status()} ${response.statusText()}`);
    }

    const body = await response.text();
    fs.writeFileSync(filePath, body);
    console.log('M3U file saved successfully at', filePath);

    await browser.close();
  } catch (err) {
    console.error('Error fetching M3U:', err);
    process.exit(1);
  }
})();
