const fs = require('fs');
const path = require('path');
const https = require('https');
const url = 'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true';

// HTTP proxy config
const proxy = { host: '222.252.194.29', port: 8080 }; // HTTP proxy

const filePath = path.join(process.cwd(), 'bingcha.m3u');

const options = {
  host: proxy.host,
  port: proxy.port,
  method: 'CONNECT',
  path: 'fy.188766.xyz:443',
};

const req = https.request(options);
req.on('connect', (res, socket, head) => {
  https.get({
    host: 'fy.188766.xyz',
    path: '/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true',
    agent: new https.Agent({ socket }),
    headers: { 'User-Agent': 'curl/8.13.0' },
  }, (res) => {
    let data = '';
    res.on('data', chunk => data += chunk);
    res.on('end', () => {
      fs.writeFileSync(filePath, data);
      console.log('M3U saved successfully:', filePath);
    });
  });
});
req.end();
