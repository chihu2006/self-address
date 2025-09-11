const { chromium } = require('playwright');
const fs = require('fs');
const proxifly = require('proxifly'); // npm install proxifly

(async () => {
  // Get a free proxy from Proxifly
  const proxy = await proxifly.getProxy({ protocol: 'http' }); // options available

  console.log('Using proxy:', proxy);

  const browser = await chromium.launch({
    headless: true,
    proxy: { server: `http://${proxy}` }, // or `socks5://` if needed
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext();
  const page = await context.newPage();

  await page.goto(
    'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true',
    { waitUntil: 'load', timeout: 120000 }
  );

  const bodyText = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync('bingcha.m3u', bodyText);

  console.log('M3U file saved!');
  await browser.close();
})();
