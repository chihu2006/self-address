#!/usr/bin/env python3
"""
Fetch and probe TV channels:

- For .m3u8 URLs: fetch the first segment only.
- For direct streams: probe normally.
- Logs real-time latency, status, and grabbed bytes.
"""

import sys
import os
import re
import time
import requests
from requests.exceptions import RequestException
from urllib.parse import urljoin, urlparse

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
if os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or \
   os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"):
    PROXIES = {
        "http": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
        "https": os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
    }

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
            m = re.search(r",(.+)$", ln)
            name = m.group(1).strip() if m else f"Channel {len(channels)+1}"
            i += 1
            while i < len(lines) and lines[i].startswith("#"):
                i += 1
            if i < len(lines):
                url = lines[i]
                channels.append({"name": name, "url": url})
        i += 1
    return channels

def probe_url(url, headers, timeout_head=HEAD_TIMEOUT, timeout_get=GET_TIMEOUT):
    """Probe a URL using HEAD + small GET; return status, latency, and bytes."""
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

def probe_first_segment(final_url, headers):
    """Fetch first segment from a .m3u8 playlist and probe it."""
    try:
        r = requests.get(final_url, headers=headers, timeout=GET_TIMEOUT, proxies=PROXIES)
        r.raise_for_status()
        lines = r.text.splitlines()
        first_segment = next((urljoin(final_url, ln.strip()) for ln in lines if ln.strip() and not ln.startswith("#")), None)
        if first_segment:
            seg_res = probe_url(first_segment, headers)
            seg_res["segment_url"] = first_segment
            return seg_res
    except Exception as e:
        return {"error": str(e), "segment_url": None}
    return {"segment_url": None}

def probe_channel(channel, uas_list):
    """Probe channel: first segment for .m3u8, direct probe otherwise."""
    for ua in uas_list:
        hdrs = DEFAULT_HEADERS.copy()
        hdrs["User-Agent"] = ua
        parsed = urlparse(channel["url"])
        if parsed.scheme and parsed.netloc:
            hdrs["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

        try:
            # Resolve final URL
            r = requests.head(channel["url"], headers=hdrs, allow_redirects=True, timeout=HEAD_TIMEOUT, proxies=PROXIES)
            final_url = r.url
        except Exception as e:
            return {"error": str(e)}

        # For .m3u8, probe first segment only
        if final_url.endswith(".m3u8"):
            seg_res = probe_first_segment(final_url, hdrs)
            if seg_res:
                seg_res["used_ua"] = ua
                return seg_res
        else:
            # Direct stream
            res = probe_url(final_url, hdrs)
            res["used_ua"] = ua
            return res
    return {"error": "Failed to probe"}

def main():
    channels = read_m3u(M3U_FILE, NUM_CHANNELS)
    print(f"Found {len(channels)} channels. Probing each...\n")

    for idx, ch in enumerate(channels, start=1):
        print(f"[{idx}/{len(channels)}] {ch['name']}")
        print(f"    Original URL: {ch['url']}")
        probe = probe_channel(ch, VLC_UAS)

        print(f"    Used UA: {probe.get('used_ua')}")
        print(f"    Final URL: {probe.get('final_url')}")
        print(f"    HEAD status: {probe.get('status_head')}  GET status: {probe.get('status_get')}")
        if probe.get("elapsed_head"):
            print(f"    HEAD elapsed: {probe['elapsed_head']:.3f}s")
        if probe.get("elapsed_get"):
            print(f"    GET elapsed: {probe['elapsed_get']:.3f}s")
        if probe.get("grabbed_bytes_len"):
            print(f"    Grabbed bytes: {probe['grabbed_bytes_len']} preview(hex): {probe['grabbed_bytes_preview']}")
        if "segment_url" in probe:
            print(f"    First segment URL: {probe.get('segment_url')}")
        if probe.get("error"):
            print(f"    ERROR: {probe['error']}")
        print("-" * 72)
        time.sleep(0.25)

if __name__ == "__main__":
    main()
