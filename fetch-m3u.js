const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const Proxifly = require('proxifly');

// Initialize Proxifly client
const proxifly = new Proxifly({
  apiKey: '8Erh9PqTFMH8xmpHoABsJXTkvutHM62D6WanPXWcUy9E' // optional, but better
});

// Proxifly options (request only 1 proxy)
const options = {
  protocol: 'http',       // http | socks4 | socks5
  anonymity: 'elite',     // transparent | anonymous | elite
  country: 'US',          // country filter
  https: true,            // must support HTTPS
  speed: 10000,           // latency filter (ms)
  format: 'json',         
  quantity: 1             // only one proxy
};

(async () => {
  try {
    console.log(`Fetching a proxy from Proxifly...`);
    const proxyList = await proxifly.getProxy(options);
    if (!proxyList || proxyList.length === 0) {
      throw new Error('No proxy returned');
    }

    const proxy = proxyList[0];
    console.log('Using proxy:', proxy.ip + ':' + proxy.port);

    const browser = await chromium.launch({
      headless: true,
      proxy: { server: `${options.protocol}://${proxy.ip}:${proxy.port}` },
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
  } catch (err) {
    console.error('Failed to fetch M3U:', err.message);
    process.exit(1);
  }
})();
