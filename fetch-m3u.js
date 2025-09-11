const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const https = require('https');

const PROXY_LIST_URL = 'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt';
const MAX_RETRIES = 50; // Max proxies to try

function fetchProxyList() {
  return new Promise((resolve, reject) => {
    https.get(PROXY_LIST_URL, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        const proxies = data.split('\n').map(line => line.trim()).filter(Boolean);
        resolve(proxies);
      });
    }).on('error', reject);
  });
}

(async () => {
  let success = false;

  try {
    console.log('Fetching proxy list...');
    const proxies = await fetchProxyList();
    if (!proxies.length) throw new Error('No proxies found');

    // Shuffle proxies for randomness
    const shuffledProxies = proxies.sort(() => 0.5 - Math.random());

    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
      const proxy = shuffledProxies[attempt - 1];
      console.log(`Attempt ${attempt}/${MAX_RETRIES}: Trying proxy ${proxy}`);

      try {
        const browser = await chromium.launch({
          headless: true,
          proxy: { server: `socks5://${proxy}` },
          args: ['--no-sandbox', '--disable-setuid-sandbox']
        });

        const context = await browser.newContext({
          userAgent:
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          extraHTTPHeaders: { 'Accept-Language': 'en-US,en;q=0.9' }
        });

        const page = await context.newPage();

        await page.goto(
          'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true',
          { waitUntil: 'load', timeout: 120000 }
        );

        const bodyText = await page.evaluate(() => document.body.innerText);

        const filePath = path.join(process.cwd(), 'bingcha.m3u');
        fs.writeFileSync(filePath, bodyText);
        console.log('✅ M3U file saved successfully!');

        await browser.close();
        success = true;
        break; // Stop retrying if successful
      } catch (err) {
        console.warn(`❌ Proxy ${proxy} failed: ${err.message}`);
      }
    }

    if (!success) {
      console.error(`All ${MAX_RETRIES} proxies failed. Could not fetch M3U.`);
      process.exit(1);
    }
  } catch (err) {
    console.error('Unexpected error:', err.message);
    process.exit(1);
  }
})();
