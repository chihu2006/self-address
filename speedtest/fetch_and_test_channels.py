#!/usr/bin/env python3
import sys
import os
import re
import time
import csv
import requests
from requests.exceptions import RequestException, Timeout
from urllib.parse import urljoin

# === Config ===
M3U_FILE = os.path.join("rawaddress", "freetv.m3u")
OUT_DIR = os.path.join("processed_freetv_address")
os.makedirs(OUT_DIR, exist_ok=True)

READ_BYTES = 4096
CONNECT_TIMEOUT = 10  # connect timeout
READ_TIMEOUT = 5      # max read timeout per segment
CHANNEL_MAX_TIME = 20 # max seconds per channel (including playlist + segment)
SLEEP_BETWEEN = 0.25

VLC_HEADERS = {
    "User-Agent": "VLC/3.0.18 LibVLC/3.0.18",
    "Accept": "*/*",
    "Connection": "keep-alive",
    "Icy-MetaData": "1",
    "Referer": "https://freetv.fun/",
    "Range": f"bytes=0-{READ_BYTES-1}",
}

# === Helpers ===
def parse_range(arg):
    match = re.match(r"(\d+)\s*-\s*(\d+)", arg)
    if not match:
        raise ValueError("Range must be in format start-end, e.g. 1-50")
    start, end = int(match.group(1)), int(match.group(2))
    return (min(start, end), max(start, end))

RANGE_INPUT = sys.argv[1] if len(sys.argv) > 1 else "1-20"
START_INDEX, END_INDEX = parse_range(RANGE_INPUT)

def read_m3u(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"M3U file not found: {path}")
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
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
                entries.append((extinf, lines[j]))
            i = j
        else:
            i += 1
    return entries

def is_valid_mpegts(data: bytes) -> bool:
    if len(data) < 188:
        return False
    return any(data[i] == 0x47 for i in range(min(188, len(data))))

def probe_url(url):
    res = {
        "url": url, "status": None, "elapsed": None, "bytes": 0,
        "data": b"", "content_type": "", "error": None
    }
    try:
        t0 = time.time()
        r = requests.get(
            url, headers=VLC_HEADERS, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            stream=True, allow_redirects=True
        )
        res["elapsed"] = time.time() - t0
        res["status"] = r.status_code
        res["content_type"] = r.headers.get("Content-Type", "")
        if r.status_code in (200, 206):
            data = r.raw.read(READ_BYTES)
            res["bytes"] = len(data)
            res["data"] = data
        r.close()
    except Timeout as e:
        res["error"] = f"Timeout: {str(e)}"
    except RequestException as e:
        res["error"] = str(e)
    return res

def probe_first_segment(m3u_url):
    """Fetch playlist and first segment with per-channel timeout."""
    result = {
        "status": None, "bytes": 0, "data": b"", "content_type": "",
        "segment_url": None, "error": None, "ended": False, "elapsed": None
    }
    start_time = time.time()
    try:
        r = requests.get(m3u_url, headers=VLC_HEADERS, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        r.raise_for_status()
        result["status"] = r.status_code
        result["content_type"] = r.headers.get("Content-Type", "")
        text = r.text
        if "#EXT-X-ENDLIST" in text:
            result["ended"] = True

        # Not HLS playlist
        if not m3u_url.endswith(".m3u8"):
            return probe_url(m3u_url)

        for line in text.splitlines():
            if time.time() - start_time > CHANNEL_MAX_TIME:
                result["error"] = "Channel max time exceeded"
                return result
            line = line.strip()
            if line and not line.startswith("#"):
                seg_url = urljoin(m3u_url, line)
                seg_res = probe_url(seg_url)
                result.update(seg_res)
                result["segment_url"] = seg_url
                break
        return result
    except Timeout as e:
        result["error"] = f"Timeout: {str(e)}"
        return result
    except RequestException as e:
        result["error"] = str(e)
        return result
    except Exception as e:
        result["error"] = str(e)
        return result

def categorize(extinf, url, probe):
    status = probe.get("status")
    data = probe.get("data", b"")
    content_type = probe.get("content_type", "").lower()
    ended = probe.get("ended", False)
    reason = ""

    if status in (200, 206):
        if ended:
            reason = "playlist ended (#EXT-X-ENDLIST)"
            return "ended_playlist", reason
        if len(data) == 0:
            reason = "no data in first segment"
            return "no_real_content", reason
        if "video" in content_type or "mpeg" in content_type or is_valid_mpegts(data):
            reason = f"status={status}, type={content_type or 'mpegts'}, bytes={len(data)}"
            return "playable", reason
        reason = f"non-video content-type ({content_type})"
        return "non_video_content", reason
    reason = f"invalid status {status} or error {probe.get('error')}"
    return "not_valid", reason

# === Main ===
def main():
    entries = read_m3u(M3U_FILE)
    selected = entries[START_INDEX - 1:END_INDEX]
    total = len(selected)
    print(f"Testing channels {START_INDEX}–{END_INDEX} ({total} total)\n")

    categorized = {}
    report_rows = []
    start_time = time.time()

    for idx, (extinf, url) in enumerate(selected, start=START_INDEX):
        elapsed_all = time.time() - start_time
        avg_time = elapsed_all / (idx - START_INDEX + 1)
        remaining = total - (idx - START_INDEX + 1)
        eta = remaining * avg_time
        eta_min = int(eta // 60)
        eta_sec = int(eta % 60)

        print(f"▶️ [{idx}/{END_INDEX}] Checking: {url}")
        print(f"   Estimated remaining: ~{eta_min}m {eta_sec}s")

        probe = probe_first_segment(url)
        cat, reason = categorize(extinf, url, probe)

        print(f"  → Status: {probe.get('status')}, Bytes: {probe.get('bytes')}, "
              f"Type: {probe.get('content_type')}, Ended: {probe.get('ended')}, "
              f"Category: {cat}")
        print(f"     Reason: {reason}\n")

        categorized.setdefault(cat, []).append((extinf, url))
        report_rows.append({
            "index": idx,
            "category": cat,
            "reason": reason,
            "url": url,
            "segment_url": probe.get("segment_url"),
            "status": probe.get("status"),
            "bytes": probe.get("bytes"),
            "elapsed": probe.get("elapsed"),
            "error": probe.get("error"),
        })

        time.sleep(SLEEP_BETWEEN)

    # Write categorized M3U files
    for cat, items in categorized.items():
        out_file = os.path.join(OUT_DIR, f"{cat}.m3u")
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for extinf, url in items:
                f.write(extinf + "\n" + url + "\n")
        print(f"✅ Saved {len(items)} entries to {out_file}")

    # Write CSV report
    report_file = os.path.join(OUT_DIR, "report_channels.csv")
    with open(report_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=list(report_rows[0].keys()))
        writer.writeheader()
        writer.writerows(report_rows)
    print(f"📄 Detailed report saved to {report_file}")

    total_time = time.time() - start_time
    print(f"\n✅ All done in {total_time:.1f}s ({total} channels tested)")
    print("Categories summary:")
    for cat, items in categorized.items():
        print(f"  {cat}: {len(items)}")

if __name__ == "__main__":
    main()
