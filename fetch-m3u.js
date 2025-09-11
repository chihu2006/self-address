const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const proxifly = new (require('proxifly'))({
  // Not required, but having one removes limits (get your key at https://proxifly.dev).
  apiKey: '8Erh9PqTFMH8xmpHoABsJXTkvutHM62D6WanPXWcUy9E'
});

const MAX_RETRIES = 50; // Max proxies to try

// Proxifly options
var options = {
  protocol: 'http', // http | socks4 | socks5
  anonymity: 'elite', // transparent | anonymous | elite
  country: 'US', // https://www.nationsonline.org/oneworld/country_code_list.htm
  https: true, // true | false
  speed: 10000, // 0 - 60000
  format: 'json', // json | text
  quantity: 1, // 1 - 20
};

(async () => {
  let success = false;

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      console.log(`Attempt ${attempt}: Fetching proxy from Proxifly...`);
      const proxyList = await proxifly.getProxy(options);
      if (!proxyList || proxyList.length === 0) throw new Error('No proxy returned');

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
      success = true;
      break; // Exit loop if successful
    } catch (err) {
      console.warn(`Attempt ${attempt} failed: ${err.message}`);
    }
  }

  if (!success) {
    console.error('All attempts failed. Could not fetch M3U.');
    process.exit(1);
  }
})();
