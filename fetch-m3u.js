const fs = require('fs');
const { exec } = require('child_process');

const PROXY = '222.252.194.29:8080';
const URL = 'https://fy.188766.xyz/?ip=192.168.1.2&proxy=true&lunbo=false&bconly=true';
const OUTPUT = 'bingcha.m3u';

console.log(`Fetching M3U via proxy ${PROXY}...`);

const cmd = `curl -x ${PROXY} -L -A "curl/8.13.0" -o ${OUTPUT} ${URL}`;

exec(cmd, (error, stdout, stderr) => {
  if (error) {
    console.error(`Error fetching M3U: ${error.message}`);
    process.exit(1);
  }
  if (stderr) console.warn(stderr);
  console.log('M3U fetch completed successfully!');
});
