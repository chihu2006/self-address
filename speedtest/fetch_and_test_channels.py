#!/usr/bin/env python3
import sys
import os
import re
import time
import csv
import requests
import signal
from urllib.parse import urljoin
from requests.exceptions import RequestException, Timeout

# === Config ===
M3U_FILE = os.path.join("rawaddress", "freetv.m3u")
OUT_DIR = os.path.join("processed_freetv_address")
os.makedirs(OUT_DIR, exist_ok=True)

READ_BYTES = 8192
MIN_SEGMENT_BYTES = 4096
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

# === Quality inference thresholds ===
BITRATE_RESOLUTION_MAP = [
    (2500, "1080p"),
    (1200, "720p"),
    (700, "480p"),
    (400, "360p"),
    (200, "240p"),
]

# === Input parsing ===
def parse_range(arg):
    match = re.match(r"(\d+)\s*-\s*(\d+)", arg)
    if not match:
        raise ValueError("Range must be in format start-end, e.g. 1-50")
    start, end = int(match.group(1)), int(match.group(2))
    return min(start, end), max(start, end)

RANGE_INPUT = sys.argv[1] if len(sys.argv) > 1 else "1-20"
START_INDEX, END_INDEX = parse_range(RANGE_INPUT)

# === Helpers ===
def is_valid_mpegts(data: bytes) -> bool:
    packet_count = min(3, len(data) // 188)
    if packet_count < 1:
        return False
    for i in range(packet_count):
        if data[i * 188] != 0x47:
            return False
    return True

def extract_resolution_from_text(text):
    match = re.search(r"RESOLUTION=(\d+)x(\d+)", text, re.IGNORECASE)
    if match:
        w, h = map(int, match.groups())
        if h >= 1000: return "1080p"
        if h >= 700: return "720p"
        if h >= 500: return "480p"
        if h >= 350: return "360p"
        return f"{w}x{h}"

    match = re.search(r"(\d{3,4})[pP](?!\w)", text)
    if match:
        return f"{match.group(1)}p"

    match = re.search(r"(\d{3,4})x(\d{3,4})", text)
    if match:
        w, h = map(int, match.groups())
        if h >= 1000: return "1080p"
        if h >= 700: return "720p"
        if h >= 500: return "480p"
        if h >= 350: return "360p"
        return f"{w}x{h}"
    return None

def infer_resolution_from_bitrate(bitrate_kbps):
    for limit, res in BITRATE_RESOLUTION_MAP:
        if bitrate_kbps >= limit:
            return res
    return "low"

def probe_url(url):
    res = {
        "url": url, "status": None, "elapsed": None, "bytes": 0,
        "data": b"", "content_type": "", "error": None, "final_url": url
    }
    try:
        t0 = time.time()
        r = requests.get(url, headers=VLC_HEADERS, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), stream=True)
        res["status"] = r.status_code
        res["content_type"] = r.headers.get("Content-Type", "")
        data = b""
        for chunk in r.iter_content(chunk_size=512):
            data += chunk
            if len(data) >= READ_BYTES:
                break
        res["bytes"] = len(data)
        res["data"] = data
        res["elapsed"] = time.time() - t0
        r.close()
    except Timeout as e:
        res["error"] = f"Timeout: {e}"
    except RequestException as e:
        res["error"] = str(e)
    return res

# === Core logic ===
def probe_first_segment(m3u_url, depth=0):
    result = {
        "status": None, "bytes": 0, "data": b"", "content_type": "",
        "segment_url": None, "final_url": m3u_url, "error": None,
        "ended": False, "elapsed": None, "segments_tested": 0,
        "valid_segments": 0, "manifest_valid": False,
        "continuity_ok": True, "has_extinf": False,
        "avg_segment_duration": None, "segment_count": 0,
        "bitrate_kbps": 0, "resolution": None, "encrypted": False
    }

    if depth > MAX_PLAYLIST_DEPTH:
        result["error"] = "Max playlist recursion exceeded"
        return result

    try:
        r = requests.get(m3u_url, headers=VLC_HEADERS, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        r.raise_for_status()
        text = r.text
        result["status"] = r.status_code
        result["content_type"] = r.headers.get("Content-Type", "")
        result["manifest_valid"] = "#EXTM3U" in text
        result["has_extinf"] = "#EXTINF" in text
        result["ended"] = "#EXT-X-ENDLIST" in text
        result["encrypted"] = "#EXT-X-KEY" in text

        result["resolution"] = extract_resolution_from_text(text)

        lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
        result["segment_count"] = len(lines)

        if not lines:
            result["error"] = "No segments found"
            return result

        seg_urls = []
        for i in range(min(3, len(lines))):
            seg_url = urljoin(m3u_url, lines[i])
            seg_urls.append(seg_url)

        total_bytes = 0
        valid_segments = 0
        total_elapsed = 0.0
        for seg_url in seg_urls:
            seg_res = probe_url(seg_url)
            result["segment_url"] = seg_url
            if seg_res["bytes"] >= MIN_SEGMENT_BYTES and is_valid_mpegts(seg_res["data"]):
                valid_segments += 1
                total_bytes += seg_res["bytes"]
                total_elapsed += seg_res["elapsed"] or 0
        result["segments_tested"] = len(seg_urls)
        result["valid_segments"] = valid_segments

        if total_elapsed > 0:
            bitrate_kbps = (total_bytes * 8 / total_elapsed) / 1000
            result["bitrate_kbps"] = round(bitrate_kbps, 1)
        if not result.get("resolution"):
            result["resolution"] = infer_resolution_from_bitrate(result["bitrate_kbps"])
        result["final_url"] = seg_urls[0] if seg_urls else m3u_url
        return result

    except Timeout as e:
        result["error"] = f"Timeout: {e}"
        return result
    except RequestException as e:
        result["error"] = str(e)
        return result
    except Exception as e:
        result["error"] = str(e)
        return result

def categorize(extinf, url, probe):
    if probe.get("error"):
        return "not_valid", probe["error"]

    if probe.get("encrypted"):
        return "encrypted", "stream encrypted"

    valid_segments = probe.get("valid_segments", 0)
    if valid_segments == 0:
        return "not_valid", "no valid TS segments"

    bitrate = probe.get("bitrate_kbps", 0)
    if bitrate < 300:
        return "low_quality", f"low bitrate {bitrate} kbps"

    if probe.get("ended"):
        return "ended_playlist", "#EXT-X-ENDLIST found"

    return "playable", f"{valid_segments}/{probe.get('segments_tested')} segments passed, bitrate={bitrate} kbps"

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

        def timeout_handler(signum, frame):
            raise TimeoutError("Channel max time exceeded")

        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(CHANNEL_MAX_TIME)
        try:
            probe = probe_first_segment(url)
        except TimeoutError:
            probe = {"status": None, "bytes": 0, "error": "Channel max time exceeded", "final_url": url}
        finally:
            signal.alarm(0)

        cat, reason = categorize(extinf, url, probe)
        print(f"  → Category: {cat} | {reason}\n")

        categorized.setdefault(cat, []).append((extinf, url))
        report_rows.append({
            "index": idx,
            "category": cat,
            "reason": reason,
            "url": url,
            "segment_url": probe.get("segment_url"),
            "final_url": probe.get("final_url"),
            "status": probe.get("status"),
            "bytes": probe.get("bytes"),
            "elapsed": probe.get("elapsed"),
            "error": probe.get("error"),
            "encrypted": probe.get("encrypted"),
            "segments_tested": probe.get("segments_tested"),
            "valid_segments": probe.get("valid_segments"),
            "manifest_valid": probe.get("manifest_valid"),
            "continuity_ok": probe.get("continuity_ok"),
            "has_extinf": probe.get("has_extinf"),
            "avg_segment_duration": probe.get("avg_segment_duration"),
            "segment_count": probe.get("segment_count"),
            "bitrate_kbps": probe.get("bitrate_kbps"),
            "resolution": probe.get("resolution"),
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
    if report_rows:
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
