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

# === Input parsing ===
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


# === Utility functions ===
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


def probe_url(url):
    """Fetch a URL partially and measure response quality."""
    res = {
        "url": url,
        "status": None,
        "elapsed": None,
        "bytes": 0,
        "error": None,
        "data": b"",
        "content_type": "",
    }
    try:
        t0 = time.time()
        r = requests.get(
            url, headers=VLC_HEADERS, timeout=TIMEOUT, stream=True, allow_redirects=True
        )
        res["elapsed"] = time.time() - t0
        res["status"] = r.status_code
        res["content_type"] = r.headers.get("Content-Type", "")
        if r.status_code in (200, 206):
            data = r.raw.read(READ_BYTES)
            res["data"] = data
            res["bytes"] = len(data)
        r.close()
    except RequestException as e:
        res["error"] = str(e)
    return res


def probe_first_segment(m3u_url):
    """
    Fetch the playlist and the first media segment.
    Returns probe result dict with keys:
      - status
      - bytes
      - data
      - content_type
      - segment_url
      - ended: True if playlist contains #EXT-X-ENDLIST
    """
    result = {
        "status": None,
        "bytes": 0,
        "data": b"",
        "content_type": "",
        "segment_url": None,
        "error": None,
        "ended": False
    }

    try:
        r = requests.get(m3u_url, headers=VLC_HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        result["status"] = r.status_code
        result["content_type"] = r.headers.get("Content-Type", "")
        text = r.text

        # Detect if playlist has ended
        if "#EXT-X-ENDLIST" in text:
            result["ended"] = True

        # If not HLS or static file, probe directly
        if not m3u_url.endswith(".m3u8"):
            return probe_url(m3u_url)

        # Find first media segment
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                seg_url = urljoin(m3u_url, line)
                result.update(probe_url(seg_url))
                result["segment_url"] = seg_url
                break

        return result

    except Exception as e:
        result["error"] = str(e)
        return result

def is_valid_mpegts(data):
    """Check if data appears to be MPEG-TS with 0x47 sync bytes every 188 bytes."""
    if not data or len(data) < 188:
        return False
    sync_offsets = [i for i in range(min(188, len(data))) if data[i] == 0x47]
    for offset in sync_offsets:
        valid_packets = 0
        for i in range(offset, len(data), 188):
            if i + 188 <= len(data) and data[i] == 0x47:
                valid_packets += 1
            else:
                break
        if valid_packets >= 3:
            return True
    return False


def categorize(extinf, url, probe):
    """
    Categorize a channel based on:
    - playlist & first segment response
    - content-type
    - MPEG-TS check
    - ended streams
    """
    status = probe.get("status")
    data = probe.get("data", b"")
    content_type = probe.get("content_type", "").lower()
    ended = probe.get("ended", False)

    if status in (200, 206):
        if ended:
            return "ended_playlist"
        if len(data) == 0:
            return "no_real_content"
        if "video" in content_type or "mpeg" in content_type or is_valid_mpegts(data):
            return "playable"
        else:
            return "non_video_content"
    else:
        return "not_valid"

# === Main process ===
def main():
    entries = read_m3u(M3U_FILE)
    selected = entries[START_INDEX - 1 : END_INDEX]
    print(f"Testing channels {START_INDEX}–{END_INDEX} ({len(selected)} total)\n")

    categorized = {"playable": [], "non_video_content": [], "no_real_content": [], "not_valid": []}

    for idx, (extinf, url) in enumerate(selected, start=START_INDEX):
        print(f"[{idx}] Checking: {url}")
        seg_probe = probe_first_segment(url)
        print(
            f"  → Status: {seg_probe.get('status')}, "
            f"Bytes: {seg_probe.get('bytes')}, "
            f"Type: {seg_probe.get('content_type')}, "
            f"Ended: {seg_probe.get('ended')}, "
            f"Error: {seg_probe.get('error')}"
        )
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

    total = sum(len(v) for v in categorized.values())
    print("\n📊 Summary:")
    for cat, items in categorized.items():
        pct = (len(items) / total * 100) if total else 0
        print(f"  {cat:>16}: {len(items):3d} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
