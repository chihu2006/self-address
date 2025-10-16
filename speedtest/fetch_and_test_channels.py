import sys
import requests
import time
import os
import re

NUM_CHANNELS = int(sys.argv[1]) if len(sys.argv) > 1 else 20
M3U_FILE = os.path.join('rawaddress', 'freetv.m3u')

channels = []

# Read M3U manually
with open(M3U_FILE, 'r', encoding='utf-8', errors='ignore') as f:
    lines = [line.strip() for line in f if line.strip()]

i = 0
while i < len(lines) and len(channels) < NUM_CHANNELS:
    line = lines[i]
    if line.startswith('#EXTINF'):
        # Extract channel name from the line
        name_match = re.search(r',(.+)$', line)
        name = name_match.group(1) if name_match else f"Channel {len(channels)+1}"
        # Next line should be the URL
        i += 1
        if i < len(lines):
            url = lines[i]
            channels.append({'name': name, 'url': url})
    i += 1

print(f"Testing {len(channels)} channels...\n")

for idx, channel in enumerate(channels, start=1):
    url = channel['url']
    name = channel['name']

    try:
        start_time = time.time()
        response = requests.get(url, timeout=10)
        elapsed = time.time() - start_time
        latency = response.elapsed.total_seconds()

        print(f"[{idx}] {name}")
        print(f"    URL: {url}")
        print(f"    Status Code: {response.status_code}")
        print(f"    Response Time: {elapsed:.2f}s, Latency: {latency:.2f}s\n")
    except Exception as e:
        print(f"[{idx}] {name} FAILED: {e}\n")
