const fs = require('fs');
const https = require('https');
const { HttpsProxyAgent } = require('https-proxy-agent'); // <-- fixed import

const PROXY = 'http://222.252.194.29:8080';
const URL = 'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true';
const OUTPUT = 'bingcha.m3u';
const MAX_RETRIES = 5;

function fetchM3U(attempt = 1) {
  console.log(`Attempt ${attempt}: Fetching M3U via proxy ${PROXY}...`);
  const agent = new HttpsProxyAgent(PROXY);

  const file = fs.createWriteStream(OUTPUT);
  const req = https.get(URL, { agent, headers: { 'User-Agent': 'curl/8.13.0' } }, (res) => {
    res.pipe(file);
    file.on('finish', () => {
      file.close();
      console.log('M3U fetch completed successfully!');
    });
  });

  req.on('error', (err) => {
    fs.unlinkSync(OUTPUT, { force: true });
    console.error(`Attempt ${attempt} failed:`, err.message);
    if (attempt < MAX_RETRIES) {
      setTimeout(() => fetchM3U(attempt + 1), 5000);
    } else {
      console.error('All attempts failed. Could not fetch M3U.');
      process.exit(1);
    }
  });
}

fetchM3U();
