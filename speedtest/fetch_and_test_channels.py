#!/usr/bin/env python3
"""
speedtest/fetch_and_test_channels.py

Usage:
    python speedtest/fetch_and_test_channels.py [NUM_CHANNELS]

Reads rawaddress/freetv.m3u, extracts the first NUM_CHANNELS channels (default 20),
and probes each URL using VLC-like headers and small-range requests to attempt to
bypass simple UA/referrer-based 403 blocks.

Logs realtime to stdout.
"""

import sys
import os
import re
import time
import requests
from requests.exceptions import RequestException

NUM_CHANNELS = int(sys.argv[1]) if len(sys.argv) > 1 else 20
M3U_FILE = os.path.join("rawaddress", "freetv.m3u")
READ_BYTES = 1024    # how many bytes to fetch when probing the stream
HEAD_TIMEOUT = 8
GET_TIMEOUT = 12

# VLC-like User-Agent strings (common patterns). We'll try the first and fall back if needed.
VLC_UAS = [
    "VLC/3.0.18 LibVLC/3.0.18",                    # VLC style
    "VLC/3.0.16 LibVLC/3.0.16",                    # other common VLC
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "  # fallback browser-like
    " Chrome/117.0.0.0 Safari/537.36"
]

DEFAULT_HEADERS = {
    # We'll set the User-Agent per attempt
    "Accept": "*/*",
    "Connection": "keep-alive",
    # Many audio streams respond better when ICY metadata is requested
    "Icy-MetaData": "1",
    # Some servers require a referer — set to the playlist host by default
    "Referer": "https://freetv.fun/",
    # Accept range so we can do small probes
    "Range": f"bytes=0-{READ_BYTES-1}",
}

# Respect proxies from environment (HTTP_PROXY/HTTPS_PROXY)
PROXIES = None
if os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"):
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
            # name is after the last comma
            m = re.search(r",(.+)$", ln)
            name = m.group(1).strip() if m else f"Channel {len(channels)+1}"
            # next non-empty line should be the URL
            i += 1
            # skip until a non-comment line that looks like a URL
            while i < len(lines) and lines[i].startswith("#"):
                i += 1
            if i < len(lines):
                url = lines[i]
                channels.append({"name": name, "url": url})
        i += 1
    return channels

def probe_url(url, headers, timeout_head=HEAD_TIMEOUT, timeout_get=GET_TIMEOUT):
    """
    Try HEAD first (fast). If HEAD returns a disallowed status or lacks content-type,
    perform a small ranged GET to fetch bytes and check for 200/206.
    Returns dict with details.
    """
    result = {
        "orig_url": url,
        "final_url": None,
        "status_head": None,
        "status_get": None,
        "elapsed_head": None,
        "elapsed_get": None,
        "server_headers": None,
        "grabbed_bytes_len": 0,
        "grabbed_bytes_preview": None,
        "error": None,
    }

    session = requests.Session()
    try:
        t0 = time.time()
        # HEAD: allow redirects to be followed to reveal final URL
        head = session.head(url, headers=headers, timeout=timeout_head, allow_redirects=True, proxies=PROXIES)
        result["elapsed_head"] = time.time() - t0
        result["status_head"] = head.status_code
        result["final_url"] = head.url
        result["server_headers"] = dict(head.headers)
        # If HEAD is 200/206 -> good sign; if 403 we will still try GET with same headers
        if head.status_code in (200, 206):
            # Try a small ranged GET to validate actual content bytes
            t1 = time.time()
            get = session.get(head.url, headers=headers, timeout=timeout_get, stream=True, allow_redirects=True, proxies=PROXIES)
            result["elapsed_get"] = time.time() - t1
            result["status_get"] = get.status_code
            result["final_url"] = get.url
            result["server_headers"].update(get.headers)
            if get.status_code in (200, 206):
                # read a small chunk
                chunk = get.raw.read(READ_BYTES) or b""
                result["grabbed_bytes_len"] = len(chunk)
                result["grabbed_bytes_preview"] = chunk[:64].hex()
        else:
            # HEAD not good (403, 404, etc). Attempt GET probe anyway (some servers answer GET but not HEAD)
            t2 = time.time()
            get2 = session.get(url, headers=headers, timeout=timeout_get, stream=True, allow_redirects=True, proxies=PROXIES)
            result["elapsed_get"] = time.time() - t2
            result["status_get"] = get2.status_code
            result["final_url"] = get2.url
            result["server_headers"] = dict(get2.headers)
            if get2.status_code in (200, 206):
                chunk = get2.raw.read(READ_BYTES) or b""
                result["grabbed_bytes_len"] = len(chunk)
                result["grabbed_bytes_preview"] = chunk[:64].hex()
    except RequestException as e:
        result["error"] = str(e)
    finally:
        session.close()

    return result

def attempt_probe_with_uas(channel, uas_list):
    """Try probing the channel URL with multiple UAs (VLC-like then browser) and return the best response."""
    for ua in uas_list:
        hdrs = DEFAULT_HEADERS.copy()
        hdrs["User-Agent"] = ua
        # Update Referer to host of URL if possible (some servers require matching referer)
        try:
            from urllib.parse import urlparse
            parsed = urlparse(channel["url"])
            if parsed.scheme and parsed.netloc:
                hdrs["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
        except Exception:
            pass

        print(f"    -> trying User-Agent: {ua!r}")
        res = probe_url(channel["url"], hdrs)
        # If GET returned success (200/206) and grabbed bytes, return immediately
        if res.get("status_get") in (200, 206) and res.get("grabbed_bytes_len", 0) > 0:
            res["used_ua"] = ua
            return res
        # If HEAD was 200/206 that's also promising even if GET failed to read (could be HLS)
        if res.get("status_head") in (200, 206):
            res["used_ua"] = ua
            return res
        # log and continue to next UA
        print(f"      status_head={res.get('status_head')} status_get={res.get('status_get')} error={res.get('error')}")
    # none succeeded; return last res with a marker
    res["used_ua"] = uas_list[0] if uas_list else None
    return res

def main():
    try:
        channels = read_m3u(M3U_FILE, NUM_CHANNELS)
    except Exception as e:
        print(f"ERROR: cannot read m3u file: {e}")
        sys.exit(2)

    if not channels:
        print("No channels found in M3U.")
        return

    print(f"Found {len(channels)} channels. Probing each with VLC-like headers...\n")

    for idx, ch in enumerate(channels, start=1):
        print(f"[{idx}/{len(channels)}] {ch['name']}")
        print(f"    Original URL: {ch['url']}")

        # Attempt probe with VLC-like UAs (primary) then fallback
        probe = attempt_probe_with_uas(ch, VLC_UAS)

        # Print results nicely
        print(f"    Used UA: {probe.get('used_ua')}")
        print(f"    Final URL: {probe.get('final_url')}")
        print(f"    HEAD status: {probe.get('status_head')}  GET status: {probe.get('status_get')}")
        if probe.get("elapsed_head") is not None:
            print(f"    HEAD elapsed: {probe.get('elapsed_head'):.3f}s")
        if probe.get("elapsed_get") is not None:
            print(f"    GET elapsed: {probe.get('elapsed_get'):.3f}s")
        if probe.get("server_headers"):
            sh = probe["server_headers"]
            # print a few relevant headers when present
            for h in ("content-type", "icy-br", "icy-genre", "server", "content-length", "www-authenticate"):
                if h in sh:
                    print(f"    header {h}: {sh[h]}")
        if probe.get("grabbed_bytes_len"):
            print(f"    Grabbed bytes: {probe['grabbed_bytes_len']}  preview(hex, first 64 bytes): {probe['grabbed_bytes_preview']}")
        if probe.get("error"):
            print(f"    ERROR: {probe['error']}")
        # If still 403, show advice
        if probe.get("status_get") == 403 or probe.get("status_head") == 403:
            print("    NOTE: Server returned 403. Try running from a residential IP or set HTTP_PROXY/HTTPS_PROXY to a permitted proxy.")
        print("-" * 72)
        # small sleep so logs are readable and we don't hammer
        time.sleep(0.25)

if __name__ == "__main__":
    main()
