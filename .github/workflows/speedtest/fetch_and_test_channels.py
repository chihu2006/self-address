import sys
import m3u8
import requests
import time

# Number of channels to test (default: 20)
NUM_CHANNELS = int(sys.argv[1]) if len(sys.argv) > 1 else 20
M3U_FILE = 'rawaddress/freetv.m3u'

# Load M3U
playlist = m3u8.load(M3U_FILE)

channels = playlist.segments[:NUM_CHANNELS]

print(f"Testing {len(channels)} channels...\n")

for idx, channel in enumerate(channels, start=1):
    url = channel.uri
    name = channel.title or f"Channel {idx}"

    try:
        start_time = time.time()
        response = requests.get(url, timeout=10)
        elapsed = time.time() - start_time

        status = response.status_code
        latency = response.elapsed.total_seconds()

        print(f"[{idx}] {name}")
        print(f"    URL: {url}")
        print(f"    Status Code: {status}")
        print(f"    Response Time: {elapsed:.2f}s, Latency: {latency:.2f}s")
    except Exception as e:
        print(f"[{idx}] {name} FAILED: {e}")
