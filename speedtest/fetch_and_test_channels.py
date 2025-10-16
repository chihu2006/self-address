#!/usr/bin/env python3
import sys
import os
import re
import time
import requests
from requests.exceptions import RequestException
from urllib.parse import urljoin

NUM_CHANNELS = int(sys.argv[1]) if len(sys.argv) > 1 else 20
M3U_FILE = os.path.join("rawaddress", "freetv.m3u")
READ_BYTES = 1024
HEAD_TIMEOUT = 8
GET_TIMEOUT = 12

VLC_UAS = [
    "VLC/3.0.18 LibVLC/3.0.18",
    "VLC/3.0.16 LibVLC/3.0.16",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
]

DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Connection": "keep-alive",
    "Icy-MetaData": "1",
    "Referer": "https://freetv.fun/",
    "Range": f"bytes=0-{READ_BYTES-1}",
}

PROXIES = None
if os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"):
    PROXIES = {
        "http": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
        "https": os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
    }

OUTPUT_FOLDER = "processed_freetv_address"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
PLAYABLE_FILE = os.path.join(OUTPUT_FOLDER, "playable.m3u")
NO_CONTENT_FILE = os.path.join(OUTPUT_FOLDER, "no_real_content.m3u")
NOT_VALID_FILE = os.path.join(OUTPUT_FOLDER, "not_valid.m3u")

def read_m3u(file_path, max_items):
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"M3U file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    channels = []
    i = 0
    while i < len(lines) and len(channels) < max_items:
        ln = lines[i]
        if ln.startswith("#EXTINF"):
            extinf = ln
            m = re.search(r",(.+)$", ln)
            name = m.group(1).strip() if m else f"Channel {len(channels)+1}"
            i += 1
            while i < len(lines) and lines[i].startswith("#"):
                i += 1
            if i < len(lines):
                url = lines[i]
                channels.append({"name": name, "url": url, "extinf": extinf})
        i += 1
    return channels

def probe_url(url, headers, timeout_head=HEAD_TIMEOUT, timeout_get=GET_TIMEOUT):
    result = {
        "final_url": None,
        "status_head": None,
        "status_get": None,
        "elapsed_head": None,
        "elapsed_get": None,
        "grabbed_bytes_len": 0,
        "grabbed_bytes_preview": None,
        "error": None,
    }
    session = requests.Session()
    try:
        t0 = time.time()
        head = session.head(url, headers=headers, timeout=timeout_head, allow_redirects=True, proxies=PROXIES)
        result["elapsed_head"] = time.time() - t0
        result["status_head"] = head.status_code
        result["final_url"] = head.url

        t1 = time.time()
        get = session.get(head.url, headers=headers, timeout=timeout_get, stream=True, allow_redirects=True, proxies=PROXIES)
        result["elapsed_get"] = time.time() - t1
        result["status_get"] = get.status_code
        result["final_url"] = get.url
        if get.status_code in (200, 206):
            chunk = get.raw.read(READ_BYTES) or b""
            result["grabbed_bytes_len"] = len(chunk)
            result["grabbed_bytes_preview"] = chunk[:64].hex()
    except RequestException as e:
        result["error"] = str(e)
    finally:
        session.close()
    return result

def probe_hls_first_segment(m3u8_url, headers):
    """Fetch .m3u8, extract first segment URL, probe it for bytes/latency."""
    try:
        r = requests.get(m3u8_url, headers=headers, timeout=GET_TIMEOUT, proxies=PROXIES)
        r.raise_for_status()
        content = r.text.splitlines()
        first_segment = None
        for line in content:
            line = line.strip()
            if line and not line.startswith("#"):
                first_segment = urljoin(m3u8_url, line)
                break
        if first_segment:
            seg_probe = probe_url(first_segment, headers)
            seg_probe["segment_url"] = first_segment
            return seg_probe
    except Exception as e:
        return {"error": str(e), "segment_url": None}
    return {"segment_url": None}

def attempt_probe_with_uas(channel, uas_list):
    for ua in uas_list:
        hdrs = DEFAULT_HEADERS.copy()
        hdrs["User-Agent"] = ua
        from urllib.parse import urlparse
        parsed = urlparse(channel["url"])
        if parsed.scheme and parsed.netloc:
            hdrs["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

        res = probe_url(channel["url"], hdrs)
        if res.get("status_get") in (200, 206) and res.get("grabbed_bytes_len", 0) > 0:
            res["used_ua"] = ua
            # If .m3u8, also probe first segment
            if channel["url"].endswith(".m3u8"):
                seg_res = probe_hls_first_segment(channel["url"], hdrs)
                res["first_segment"] = seg_res
            return res
    res["used_ua"] = uas_list[0] if uas_list else None
    return res

def categorize_channel(probe):
    """Categorize based on grabbed bytes preview (pattern from your test)."""
    b = probe.get("grabbed_bytes_preview") or ""
    # Playable patterns: gzip header (1f8b08), or some other known playable hex
    if b.startswith("1f8b08") or probe.get("status_get") in (200, 206) and probe.get("grabbed_bytes_len",0) >= 200:
        return "playable"
    # Valid but no content: readable playlist-like content (starts with 23 45 58 54 ... "#EXTM3U")
    elif b.startswith("23455854"):  # hex of "#EXT"
        return "no_real_content"
    else:
        return "not_valid"

def append_to_m3u(category, channel):
    """Append the EXTINF and URL to the corresponding file."""
    file_map = {
        "playable": PLAYABLE_FILE,
        "no_real_content": NO_CONTENT_FILE,
        "not_valid": NOT_VALID_FILE
    }
    target_file = file_map.get(category)
    with open(target_file, "a", encoding="utf-8") as f:
        f.write(f"{channel['extinf']}\n{channel['url']}\n")

def main():
    channels = read_m3u(M3U_FILE, NUM_CHANNELS)
    print(f"Found {len(channels)} channels. Probing each...\n")

    for idx, ch in enumerate(channels, start=1):
        print(f"[{idx}/{len(channels)}] {ch['name']}")
        print(f"    Original URL: {ch['url']}")
        probe = attempt_probe_with_uas(ch, VLC_UAS)

        print(f"    Used UA: {probe.get('used_ua')}")
        print(f"    Final URL: {probe.get('final_url')}")
        print(f"    HEAD status: {probe.get('status_head')}  GET status: {probe.get('status_get')}")
        if probe.get("elapsed_head"):
            print(f"    HEAD elapsed: {probe['elapsed_head']:.3f}s")
        if probe.get("elapsed_get"):
            print(f"    GET elapsed: {probe['elapsed_get']:.3f}s")
        if probe.get("grabbed_bytes_len"):
            print(f"    Grabbed bytes: {probe['grabbed_bytes_len']} preview(hex): {probe['grabbed_bytes_preview']}")
        if "first_segment" in probe and probe["first_segment"]:
            seg = probe["first_segment"]
            print(f"    First segment URL: {seg.get('segment_url')}")
            print(f"      Segment status: {seg.get('status_get')} bytes: {seg.get('grabbed_bytes_len')}")
        if probe.get("error"):
            print(f"    ERROR: {probe['error']}")

        # Categorize and save
        category = categorize_channel(probe)
        append_to_m3u(category, ch)
        print(f"    Categorized as: {category}")
        print("-" * 72)
        time.sleep(0.25)

if __name__ == "__main__":
    main()
