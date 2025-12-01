#!/usr/bin/env python3
import csv
import requests
import time
import hashlib
from urllib.parse import urljoin

CTV_FILE = "rawaddress/freetv_ctv.m3u"
OUTPUT_FILE = "speedtest/ctv_test_result.csv"
RETRIES = 3
TIMEOUT = 10
MAX_SEGMENTS = 5  # number of segments to test per playlist

urls = []
with open(CTV_FILE, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)

results = []
hash_map = {}

def get_content(url):
    for attempt in range(RETRIES):
        try:
            r = requests.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return r.text
        except requests.exceptions.RequestException as e:
            if attempt < RETRIES - 1:
                time.sleep(2)
            else:
                return str(e)
    return None

def hash_content(content):
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def get_segments(playlist_text, base_url):
    lines = [l.strip() for l in playlist_text.splitlines() if l.strip() and not l.startswith("#")]
    segment_urls = [urljoin(base_url, l) for l in lines[:MAX_SEGMENTS]]
    return segment_urls

for idx, url in enumerate(urls, start=1):
    result = {
        "index": idx,
        "url": url,
        "category": "non_valid",
        "reason": "",
        "status": "",
        "bytes": 0,
        "elapsed": 0,
        "error": "",
        "resolution": "",
        "url_chain": url
    }

    playlist = get_content(url)
    if playlist is None or "404" in playlist or "403" in playlist:
        result["reason"] = "fetch error or HTTP error"
    elif len(playlist.strip()) == 0:
        result["reason"] = "no valid segments found"
    else:
        content_hash = hash_content(playlist.splitlines()[:5])
        if content_hash in hash_map:
            result["category"] = "duplicate"
            result["reason"] = f"duplicate content with index {hash_map[content_hash]}"
        else:
            hash_map[content_hash] = idx
            # Segment-level testing
            segment_urls = get_segments(playlist, url)
            total_bytes, total_time = 0, 0
            max_res = ""
            playable_count = 0

            for seg_url in segment_urls:
                start = time.time()
                try:
                    r = requests.get(seg_url, timeout=TIMEOUT)
                    r.raise_for_status()
                    elapsed = time.time() - start
                    total_bytes += len(r.content)
                    total_time += elapsed
                    playable_count += 1
                    # Try to extract resolution from segment name (common in m3u8)
                    if "x" in seg_url:
                        res_part = seg_url.split("/")[-1]
                        if any(c.isdigit() for c in res_part):
                            max_res = max(max_res, res_part)
                except requests.exceptions.RequestException as e:
                    result["error"] += f"{seg_url}: {str(e)} | "

            if playable_count > 0:
                result["category"] = "playable"
                result["bytes"] = total_bytes
                result["elapsed"] = round(total_time, 2)
                result["resolution"] = max_res if max_res else ""
            else:
                result["category"] = "non_valid"
                result["reason"] = "all segments invalid or inaccessible"

    if url.endswith(".ctv") and result["category"] != "playable":
        result["category"] = "needs_manual_check"
        if not result["reason"]:
            result["reason"] = "manual verification recommended"

    results.append(result)

# Write CSV
fieldnames = ["index","category","reason","url","status","bytes","elapsed","error","resolution","url_chain"]
with open(OUTPUT_FILE, "w", newline='', encoding="utf-8") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    for row in results:
        writer.writerow(row)

print(f"Test completed. Results saved to {OUTPUT_FILE}")
