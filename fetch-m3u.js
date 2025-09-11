const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const fetch = require('node-fetch');

const PROXY_LIST_URL = 'https://raw.githubusercontent.com/proxifly/free-proxy-list/refs/heads/main/proxies/all/data.txt';
const MAX_RETRIES = 150; // max proxies to try

(async () => {
  try {
    // 1. Fetch proxy list
    const res = await fetch(PROXY_LIST_URL);
    if (!res.ok) throw new Error(`Failed to fetch proxy list: ${res.status}`);
    let proxies = (await res.text())
      .split('\n')
      .map(p => p.trim())
      .filter(Boolean);

    if (proxies.length === 0) throw new Error('No proxies found');

    // 2. Shuffle proxies to try in random order
    proxies = proxies.sort(() => Math.random() - 0.5);

    let success = false;
    const tried = new Set();

    for (let i = 0; i < Math.min(MAX_RETRIES, proxies.length); i++) {
      const proxy = proxies[i];
      tried.add(proxy);
      console.log(`Trying proxy: ${proxy}`);

      try {
        const browser = await chromium.launch({
          headless: true,
          proxy: { server: `http://${proxy}` }, // or socks5:// if proxy requires
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

        console.log('M3U file saved successfully!');
        await browser.close();
        success = true;
        break; // exit loop
      } catch (err) {
        console.warn(`Proxy ${proxy} failed: ${err.message}`);
      }
    }

    if (!success) {
      throw new Error('All proxies failed, could not fetch M3U');
    }
  } catch (err) {
    console.error('Error fetching M3U:', err);
    process.exit(1);
  }
})();
