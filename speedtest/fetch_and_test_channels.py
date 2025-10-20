#!/usr/bin/env python3
import sys
import os
import re
import time
import csv
import signal
import requests
from urllib.parse import urljoin
from requests.exceptions import RequestException, Timeout

# === Config ===
M3U_FILE = os.path.join("rawaddress", "freetv.m3u")
CTV_FILE = os.path.join("rawaddress", "freetv_ctv.m3u")
OUT_DIR = os.path.join("processed_freetv_address")
CSV_FILE = os.path.join("speedtest", "test_result.csv")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)

READ_BYTES = 188*20
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 5
CHANNEL_MAX_TIME = 25
SLEEP_BETWEEN = 0.25
MAX_PLAYLIST_DEPTH = 5

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
    return min(start, end), max(start, end)

RANGE_INPUT = sys.argv[1] if len(sys.argv) > 1 else "1-20"
START_INDEX, END_INDEX = parse_range(RANGE_INPUT)

# === Read M3U ===
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

# === Helpers ===
def is_valid_mpegts(data: bytes, min_packets=5) -> bool:
    packet_size = 188
    if len(data) < packet_size * min_packets:
        return False
    for i in range(min_packets):
        if data[i*packet_size] != 0x47:
            return False
    return True

def extract_resolution(text):
    match = re.search(r"RESOLUTION=(\d+)x(\d+)", text)
    if match:
        w, h = map(int, match.groups())
        if h >= 1000:
            return "1080p"
        if h >= 700:
            return "720p"
        if h >= 480:
            return "480p"
        if h >= 360:
            return "360p"
        return f"{w}x{h}"
    match = re.search(r"(\d{3,4})[pP](?!\w)", text)
    if match:
        return f"{match.group(1)}p"
    return None

def probe_variant_or_segment(url, depth=0):
    if depth > MAX_PLAYLIST_DEPTH:
        return None, "Too many nested playlists", [url]

    try:
        r = requests.get(url, headers=VLC_HEADERS, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        r.raise_for_status()
        text = r.text
    except Exception as e:
        return None, f"fetch error: {e}", [url]

    url_chain = [url]

    if "#EXTM3U" not in text:
        return None, "not a valid m3u8", url_chain

    variant_lines = re.findall(r"#EXT-X-STREAM-INF[^\n]*\n([^\n]+)", text)
    if variant_lines:
        best_variant = variant_lines[-1].strip()
        next_url = urljoin(url, best_variant)
        sub_info, err, sub_chain = probe_variant_or_segment(next_url, depth + 1)
        return sub_info, err, url_chain + sub_chain

    segments = re.findall(r"(?m)^[^#].+\.(ts|m4s|mp4)$", text)
    if not segments:
        return None, "no valid segments found", url_chain

    first_seg = urljoin(url, segments[0].strip())
    resolution = extract_resolution(text)
    return {"segment": first_seg, "resolution": resolution, "manifest": text}, None, url_chain

def probe_segment(url):
    try:
        t0 = time.time()
        r = requests.get(url, headers=VLC_HEADERS, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), stream=True)
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
        return {"status": None, "bytes": 0, "elapsed": 0, "content_type": "", "data": b"", "error": str(e)}

def categorize(extinf, url, probe_info):
    if not probe_info or probe_info.get("error"):
        return "not_valid", probe_info.get("error", "unknown error")

    status = probe_info.get("status")
    data = probe_info.get("data", b"")
    resolution = probe_info.get("resolution")

    if (
        status in (200, 206)
        and len(data) >= 188 * 5
        and is_valid_mpegts(data, min_packets=5)
        and resolution
    ):
        return "playable", f"status={status}, bytes={len(data)}, resolution={resolution}"
    elif status in (200, 206):
        return "not_valid", f"status={status} but segment invalid ({len(data)} bytes), resolution={resolution}"
    else:
        return "not_valid", f"status={status}, error={probe_info.get('error')}"

# === Main ===
def main():
    entries = read_m3u(M3U_FILE)
    selected = entries[START_INDEX - 1:END_INDEX]

    ctv_entries = []
    filtered_entries = []

    # Filter .ctv channels
    for extinf, url in selected:
        if url.endswith(".ctv"):
            ctv_entries.append((extinf, url))
        else:
            filtered_entries.append((extinf, url))

    # Save .ctv channels
    with open(CTV_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for extinf, url in ctv_entries:
            f.write(extinf + "\n" + url + "\n")
    print(f"✅ {len(ctv_entries)} .ctv channels saved to {CTV_FILE}")

    categorized = {}
    report_rows = []
    start_time = time.time()
    total = len(filtered_entries)
    print(f"Testing {total} non-ctv channels...\n")

    for idx, (extinf, url) in enumerate(filtered_entries, start=START_INDEX):
        elapsed_all = time.time() - start_time
        avg_time = elapsed_all / (idx - START_INDEX + 1)
        remaining = total - (idx - START_INDEX + 1)
        eta = remaining * avg_time
        print(f"▶️ [{idx}/{END_INDEX}] Checking: {url}  (ETA ~{eta/60:.1f} min)")

        def timeout_handler(signum, frame):
            raise TimeoutError("Channel max time exceeded")
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(CHANNEL_MAX_TIME)

        probe_result = None
        seg_info = None
        err_msg = None

        try:
            seg_info, err_msg, url_chain = probe_variant_or_segment(url)
            if seg_info and "segment" in seg_info:
                probe_result = probe_segment(seg_info["segment"])
            else:
                probe_result = {"status": None, "bytes": 0, "error": err_msg}
        except TimeoutError:
            probe_result = {"status": None, "bytes": 0, "error": "Channel timeout"}
        finally:
            signal.alarm(0)

        if seg_info:
            probe_result["segment_url"] = seg_info.get("segment")
            probe_result["resolution"] = seg_info.get("resolution")
        else:
            probe_result["segment_url"] = None
            probe_result["resolution"] = None

        cat, reason = categorize(extinf, url, probe_result)
        print(f"  → {cat.upper()} | {reason}")
        if probe_result["segment_url"]:
            print(f"  → Segment tested: {probe_result['segment_url']}")
        if probe_result["resolution"]:
            print(f"  → Resolution: {probe_result['resolution']}\n")

        categorized.setdefault(cat, []).append((extinf, url))
        report_rows.append({
            "index": idx,
            "category": cat,
            "reason": reason,
            "url": url,
            "segment_url": probe_result.get("segment_url"),
            "status": probe_result.get("status"),
            "bytes": probe_result.get("bytes"),
            "elapsed": probe_result.get("elapsed"),
            "error": probe_result.get("error"),
            "resolution": probe_result.get("resolution"),
            "url_chain": " > ".join(url_chain),
        })

        time.sleep(SLEEP_BETWEEN)

    # Write categorized M3U files
    for cat in ["playable", "not_valid"]:
        items = categorized.get(cat, [])
        out_file = os.path.join(OUT_DIR, f"{cat}.m3u")
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for extinf, url in items:
                f.write(extinf + "\n" + url + "\n")
        print(f"✅ Saved {len(items)} entries to {out_file}")

    # Write CSV
    if report_rows:
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=list(report_rows[0].keys()))
            writer.writeheader()
            writer.writerows(report_rows)
        print(f"📄 Detailed report saved to {CSV_FILE}")

    total_time = time.time() - start_time
    print(f"\n✅ All done in {total_time:.1f}s ({total} channels tested)")

if __name__ == "__main__":
    main()
