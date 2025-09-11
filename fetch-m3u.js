const fs = require('fs');
const fetch = require('node-fetch'); // make sure to `npm install node-fetch@2`
const HttpsProxyAgent = require('https-proxy-agent');

const PROXY = 'http://222.252.194.29:8080';
const URL = 'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true';
const OUTPUT = 'bingcha.m3u';

(async () => {
  try {
    const agent = new HttpsProxyAgent(PROXY);
    const res = await fetch(URL, { agent });
    
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);

    const data = await res.text();
    fs.writeFileSync(OUTPUT, data);
    console.log('M3U file downloaded successfully at', OUTPUT);
  } catch (err) {
    console.error('Error fetching M3U:', err);
    process.exit(1);
  }
})();
