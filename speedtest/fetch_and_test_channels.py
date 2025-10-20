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
OUT_DIR = os.path.join("processed_freetv_address")
os.makedirs(OUT_DIR, exist_ok=True)

READ_BYTES = 188*10*2
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
def is_valid_mpegts(data: bytes) -> bool:
    if len(data) < 188 * 5:  # check at least 5 packets
        return False
    for i in range(5):
        if data[i*188] != 0x47:
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


def probe_variant_or_segment(url, depth=0, url_chain=None):
    """Recursively follow .m3u8 playlists until a real media segment (.ts/.m4s/.mp4) is found"""
    if url_chain is None:
        url_chain = []

    url_chain.append(url)

    if depth > MAX_PLAYLIST_DEPTH:
        return None, "Too many nested playlists", url_chain

    try:
        r = requests.get(url, headers=VLC_HEADERS, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        r.raise_for_status()
        text = r.text
    except Exception as e:
        return None, f"fetch error: {e}", url_chain

    if "#EXTM3U" not in text:
        return None, "not a valid m3u8", url_chain

    # --- 1. Variant playlist ---
    variant_lines = re.findall(r"#EXT-X-STREAM-INF[^\n]*\n([^\n]+)", text)
    if variant_lines:
        best_variant = variant_lines[-1].strip()
        next_url = urljoin(url, best_variant)
        return probe_variant_or_segment(next_url, depth + 1, url_chain)

    # --- 2. Media segments ---
    # Prefer lines following #EXTINF
    extinf_segments = re.findall(r"(?m)^#EXTINF[^\n]*\n([^\n#]+)", text)
    if extinf_segments:
        first_seg = urljoin(url, extinf_segments[0].strip())
        resolution = extract_resolution(text)
        return {"segment": first_seg, "resolution": resolution, "manifest": text}, None, url_chain

    # --- 3. Fallback: any non-comment line that is not .m3u8 ---
    other_segments = [ln for ln in text.splitlines() if ln and not ln.startswith("#") and not ln.endswith(".m3u8")]
    if other_segments:
        first_seg = urljoin(url, other_segments[0].strip())
        resolution = extract_resolution(text)
        return {"segment": first_seg, "resolution": resolution, "manifest": text}, None, url_chain

    return None, "no valid segments found", url_chain
    
def probe_segment(url):
    """Probe a single .ts or .m4s segment"""
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
    if status in (200, 206) and len(data) > 1024 and is_valid_mpegts(data):
        return "playable", f"status={status}, bytes={len(data)}"
    elif status in (200, 206):
        return "not_valid", f"status={status} but data invalid ({len(data)} bytes)"
    else:
        return "not_valid", f"status={status}, error={probe_info.get('error')}"

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

        print(f"  → {cat.upper()} | {reason}\n")

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
            "url_chain": " > ".join(url_chain)  # <-- added this line
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
