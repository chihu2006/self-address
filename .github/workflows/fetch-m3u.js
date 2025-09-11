const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  // Launch headless browser (needed to create a context)
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();

  // Use Playwright request to fetch the M3U
  const response = await context.request.get(
    'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true',
    {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9'
      }
    }
  );

  if (!response.ok()) {
    console.error(`Failed to fetch M3U: ${response.status()}`);
    await browser.close();
    process.exit(1);
  }

  // Get the M3U content as text
  const bodyText = await response.text();
  fs.writeFileSync('bingcha.m3u', bodyText);

  console.log('M3U file saved successfully!');
  await browser.close();
})();
