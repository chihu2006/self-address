#!/usr/bin/env python3
import os
import re
import sys
import time
import csv
import signal
import requests
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# === Config ===
M3U_FILE = os.path.join("rawaddress", "freetv.m3u")
CTV_FILE = os.path.join("rawaddress", "freetv_ctv.m3u")
OUT_DIR = os.path.join("processed_freetv_address")
CSV_FILE = os.path.join("speedtest", "test_result.csv")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)

READ_BYTES = 188 * 20
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 5
CHANNEL_MAX_TIME = 30
SLEEP_BETWEEN = 0.1
MAX_PLAYLIST_DEPTH = 5
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
def parse_range(arg):
    match = re.match(r"(\d+)\s*-\s*(\d+)", arg)
    if not match:
        raise ValueError("Range must be in format start-end, e.g. 1-50")
    start, end = int(match.group(1)), int(match.group(2))
    return min(start, end), max(start, end)

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

def is_valid_mpegts(data: bytes, min_packets=5) -> bool:
    packet_size = 188
    if len(data) < packet_size * min_packets:
        return False
    for i in range(min_packets):
        if data[i * packet_size] != 0x47:
            return False
    return True

def extract_resolution(text):
    match = re.search(r"RESOLUTION=(\d+)x(\d+)", text)
    if match:
        w, h = map(int, match.groups())
        if h >= 1000: return "1080p"
        if h >= 700: return "720p"
        if h >= 480: return "480p"
        if h >= 360: return "360p"
        return f"{w}x{h}"
    match = re.search(r"(\d{3,4})[pP](?!\w)", text)
    if match:
        return f"{match.group(1)}p"
    return None

# === Probing Functions ===
def probe_segment(url, headers=VLC_HEADERS):
    """Fetch the first bytes of a TS segment and return status"""
    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.time()
            r = requests.get(url, headers=headers, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                             stream=True, allow_redirects=True)
            r.raise_for_status()
            data = b""
            for chunk in r.iter_content(chunk_size=512):
                data += chunk
                if len(data) >= READ_BYTES:
                    break
            elapsed = time.time() - t0
            return {
                "status": r.status_code,
                "bytes": len(data),
                "elapsed": elapsed,
                "content_type": r.headers.get("Content-Type", ""),
                "data": data,
                "error": None,
            }
        except Exception as e:
            last_error = str(e)
            time.sleep(0.5)
    return {"status": None, "bytes": 0, "elapsed": 0, "content_type": "", "data": b"", "error": last_error}

def probe_playlist(url, depth=0, chain=None):
    """Recursively probe HLS/variant playlists to find a playable segment"""
    if chain is None:
        chain = []
    if depth > MAX_PLAYLIST_DEPTH:
        return None, "Too many nested playlists", chain
    chain.append(url)
    try:
        r = requests.get(url, headers=VLC_HEADERS, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        r.raise_for_status()
        text = r.text
    except Exception as e:
        return None, f"fetch error: {e}", chain

    if "#EXTM3U" not in text:
        return None, "not a valid m3u8", chain

    # Check for variants
    variant_lines = re.findall(r"#EXT-X-STREAM-INF[^\n]*\n([^\n]+)", text)
    for var in variant_lines:
        next_url = urljoin(url, var.strip())
        result, err, chain2 = probe_playlist(next_url, depth + 1, chain.copy())
        if result:
            return result, None, chain2

    # Otherwise, check segments
    segments = re.findall(r"(?m)^[^#].+\.(ts|m4s|mp4)$", text)
    if not segments:
        return None, "no valid segments found", chain
    for seg in segments:
        seg_url = urljoin(url, seg.strip())
        probe = probe_segment(seg_url)
        if probe["status"] in (200, 206) and len(probe["data"]) > 1024:
            resolution = extract_resolution(text)
            return {"segment": seg_url, "resolution": resolution, "manifest": text}, None, chain
    return None, "all segments invalid or inaccessible", chain

def categorize(probe_info):
    if not probe_info or probe_info.get("error"):
        return "not_valid", probe_info.get("error", "unknown error")
    status = probe_info.get("status")
    data = probe_info.get("data", b"")
    if status in (200, 206) and len(data) >= 188*5 and is_valid_mpegts(data):
        return "playable", None
    return "not_valid", f"status={status}, bytes={len(data)}, error={probe_info.get('error')}"

# === Main Channel Test ===
def test_channel(extinf, url, index):
    try:
        seg_info, err_msg, chain = probe_playlist(url)
        probe_result = probe_segment(seg_info["segment"]) if seg_info else {"status": None, "bytes": 0, "error": err_msg}
        if seg_info:
            probe_result["segment_url"] = seg_info.get("segment")
            probe_result["resolution"] = seg_info.get("resolution")
        else:
            probe_result["segment_url"] = None
            probe_result["resolution"] = None
        cat, reason = categorize(probe_result)
        return {
            "index": index,
            "category": cat,
            "reason": reason or "",
            "url": url,
            "segment_url": probe_result.get("segment_url"),
            "status": probe_result.get("status"),
            "bytes": probe_result.get("bytes"),
            "elapsed": probe_result.get("elapsed"),
            "error": probe_result.get("error"),
            "resolution": probe_result.get("resolution"),
            "url_chain": " > ".join(chain),
        }, cat, extinf, url
    except Exception as e:
        return {"index": index, "category": "not_valid", "reason": str(e), "url": url}, "not_valid", extinf, url

def main():
    entries = read_m3u(M3U_FILE)
    selected = entries[START_INDEX-1:END_INDEX]

    # Separate CTV and normal channels
    ctv_entries = [(e, u) for e,u in selected if u.endswith(".ctv")]
    normal_entries = [(e, u) for e,u in selected if not u.endswith(".ctv")]

    with open(CTV_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for extinf, url in ctv_entries:
            f.write(extinf+"\n"+url+"\n")

    print(f"✅ {len(ctv_entries)} .ctv channels saved to {CTV_FILE}")

    # Parallel testing
    report_rows = []
    categorized = {"playable": [], "not_valid": []}
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = {executor.submit(test_channel, extinf, url, idx+START_INDEX): (extinf,url) for idx,(extinf,url) in enumerate(normal_entries)}
        for future in as_completed(futures):
            row, cat, extinf, url = future.result()
            categorized.setdefault(cat, []).append((extinf,url))
            report_rows.append(row)
            print(f"[{row['index']}] {url} → {cat.upper()} | {row.get('reason')}")

    # Save M3U files
    for cat in ["playable", "not_valid"]:
        items = categorized.get(cat, [])
        out_file = os.path.join(OUT_DIR, f"{cat}.m3u")
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for extinf, url in items:
                f.write(extinf+"\n"+url+"\n")
        print(f"✅ Saved {len(items)} entries to {out_file}")

    # Save CSV
    if report_rows:
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=list(report_rows[0].keys()))
            writer.writeheader()
            writer.writerows(report_rows)
        print(f"📄 Detailed report saved to {CSV_FILE}")

if __name__ == "__main__":
    main()
