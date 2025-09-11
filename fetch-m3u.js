const fs = require('fs');
const path = require('path');
const fetch = require('node-fetch');
const { HttpsProxyAgent } = require('https-proxy-agent');

const proxy = 'http://222.252.194.29:8080';
const url = 'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true';

(async () => {
  try {
    console.log(`Fetching M3U via proxy: ${proxy}`);

    const agent = new HttpsProxyAgent(proxy);

    const res = await fetch(url, {
      agent,
      headers: { 'User-Agent': 'curl/8.13.0', 'Accept': '*/*' },
      timeout: 120000
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const body = await res.text();
    const filePath = path.join(process.cwd(), 'bingcha.m3u');
    fs.writeFileSync(filePath, body);

    console.log('M3U saved successfully:', filePath);
  } catch (err) {
    console.error('Error fetching M3U:', err);
    process.exit(1);
  }
})();
