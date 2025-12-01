#!/usr/bin/env python3
import os
import csv
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# === Config ===
CTV_FILE = "rawaddress/freetv_ctv.m3u"
OUTPUT_FILE = "speedtest/ctv_test_result.csv"
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

READ_BYTES = 188 * 20
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 5
MAX_RETRIES = 2
THREADS = 8

VLC_HEADERS = {
    "User-Agent": "VLC/3.0.18 LibVLC/3.0.18",
    "Accept": "*/*",
    "Connection": "keep-alive",
    "Icy-MetaData": "1",
    "Referer": "https://freetv.fun/",
    "Range": f"bytes=0-{READ_BYTES-1}",
}

# === Utility Functions ===
def is_valid_mpegts(data, min_packets=5):
    packet_size = 188
    if len(data) < packet_size * min_packets:
        return False
    for i in range(min_packets):
        if data[i * packet_size] != 0x47:
            return False
    return True

def probe_url(url):
    """Fetch the first bytes of a URL, check for TS validity."""
    chain = [url]
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.time()
            r = requests.get(url, headers=VLC_HEADERS, allow_redirects=True,
                             timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), stream=True)
            r.raise_for_status()
            final_url = r.url
            data = b""
            for chunk in r.iter_content(chunk_size=512):
                data += chunk
                if len(data) >= READ_BYTES:
                    break
            elapsed = time.time() - t0
            status = r.status_code
            valid_ts = is_valid_mpegts(data)
            if valid_ts:
                category = "playable"
                reason = None
            else:
                category = "not_valid"
                reason = "TS packets invalid or too short"
            return {
                "original_url": url,
                "final_url": final_url,
                "status": status,
                "bytes": len(data),
                "elapsed": round(elapsed, 2),
                "error": reason,
                "url_chain": " > ".join(chain) + f" > {final_url}" if final_url != url else url
            }
        except Exception as e:
            last_error = str(e)
            time.sleep(0.5)
    return {
        "original_url": url,
        "final_url": "",
        "status": "",
        "bytes": 0,
        "elapsed": 0,
        "error": last_error,
        "url_chain": " > ".join(chain)
    }

# === Main Script ===
def main():
    urls = []
    with open(CTV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)

    results = []
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        future_to_url = {executor.submit(probe_url, url): url for url in urls}
        for future in as_completed(future_to_url):
            res = future.result()
            results.append(res)
            print(f"[{res['status']}] {res['original_url']} -> {res['error'] or 'playable'}")

    # Save CSV
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["original_url", "final_url", "status",
                                               "bytes", "elapsed", "error", "url_chain"])
        writer.writeheader()
        writer.writerows(results)

    print(f"✅ .ctv test result saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
