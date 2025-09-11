const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Listen for the download
  page.on('download', async (download) => {
    const filePath = path.join(process.cwd(), 'bingcha.m3u');
    await download.saveAs(filePath);
    console.log('M3U file downloaded successfully!');
  });

  // Trigger the download
  await page.goto('https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true', {
    waitUntil: 'domcontentloaded'
  });

  await browser.close();
})();
