#!/usr/bin/env python3
import sys
import os
import re
import time
import requests
from requests.exceptions import RequestException
from urllib.parse import urljoin

# === Config ===
M3U_FILE = os.path.join("rawaddress", "freetv.m3u")
OUT_DIR = os.path.join("processed_freetv_address")
os.makedirs(OUT_DIR, exist_ok=True)

READ_BYTES = 1024
TIMEOUT = 10
SLEEP_BETWEEN = 0.25

VLC_HEADERS = {
    "User-Agent": "VLC/3.0.18 LibVLC/3.0.18",
    "Accept": "*/*",
    "Connection": "keep-alive",
    "Icy-MetaData": "1",
    "Referer": "https://freetv.fun/",
    "Range": f"bytes=0-{READ_BYTES-1}",
}

# === Parse input ===
def parse_range(arg):
    match = re.match(r"(\d+)\s*-\s*(\d+)", arg)
    if not match:
        raise ValueError("Range must be in format start-end, e.g. 1-50")
    start, end = int(match.group(1)), int(match.group(2))
    if start > end:
        start, end = end, start
    return start, end

RANGE_INPUT = sys.argv[1] if len(sys.argv) > 1 else "1-20"
START_INDEX, END_INDEX = parse_range(RANGE_INPUT)

# === Read M3U file ===
def read_m3u(file_path):
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"M3U file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    entries = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF"):
            extinf = lines[i]
            j = i + 1
            while j < len(lines) and lines[j].startswith("#"):
                j += 1
            if j < len(lines):
                url = lines[j]
                entries.append((extinf, url))
            i = j
        else:
            i += 1
    return entries

# === Probe URL ===
def probe_url(url):
    res = {"url": url, "status": None, "elapsed": None, "bytes": 0, "error": None}
    try:
        t0 = time.time()
        r = requests.get(url, headers=VLC_HEADERS, timeout=TIMEOUT, stream=True, allow_redirects=True)
        res["elapsed"] = time.time() - t0
        res["status"] = r.status_code
        if r.status_code in (200, 206):
            data = r.raw.read(READ_BYTES)
            res["bytes"] = len(data)
        r.close()
    except RequestException as e:
        res["error"] = str(e)
    return res

# === Probe first segment ===
def probe_first_segment(m3u_url):
    try:
        r = requests.get(m3u_url, headers=VLC_HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        for line in r.text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                seg_url = urljoin(m3u_url, line)
                seg_res = probe_url(seg_url)
                seg_res["segment_url"] = seg_url
                return seg_res
    except Exception as e:
        return {"error": str(e), "segment_url": None}
    return {"segment_url": None}

# === Categorization ===
def categorize(extinf, url, probe):
    if probe.get("status") in (200, 206) and probe.get("bytes", 0) > 0:
        return "playable"
    elif probe.get("status") in (200, 206) and probe.get("bytes", 0) == 0:
        return "no_real_content"
    else:
        return "not_valid"

# === Main ===
def main():
    entries = read_m3u(M3U_FILE)
    selected = entries[START_INDEX - 1:END_INDEX]
    print(f"Testing channels {START_INDEX}–{END_INDEX} ({len(selected)} total)\n")

    categorized = {"playable": [], "no_real_content": [], "not_valid": []}

    for idx, (extinf, url) in enumerate(selected, start=START_INDEX):
        print(f"[{idx}] Checking: {url}")
        seg_probe = probe_first_segment(url)
        print(f"  → Status: {seg_probe.get('status')}, Bytes: {seg_probe.get('bytes')}, Error: {seg_probe.get('error')}")
        category = categorize(extinf, url, seg_probe)
        categorized[category].append((extinf, url))
        time.sleep(SLEEP_BETWEEN)

    # Write categorized M3U files
    for cat, items in categorized.items():
        out_file = os.path.join(OUT_DIR, f"{cat}.m3u")
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for extinf, url in items:
                f.write(extinf + "\n" + url + "\n")
        print(f"✅ Saved {len(items)} entries to {out_file}")

if __name__ == "__main__":
    main()
