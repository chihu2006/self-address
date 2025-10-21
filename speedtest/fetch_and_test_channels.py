import requests
import m3u8
import time
import csv
import os

# Input and output paths
RAW_PLAYLIST = "rawaddress/freetv.m3u"
OUTPUT_CSV = "speedtest/test_result.csv"
PROCESSED_PLAYABLE = "processed_freetv_address/playable.m3u"
PROCESSED_NOT_VALID = "processed_freetv_address/not_valid.m3u"

# Ensure output folders exist
os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
os.makedirs(os.path.dirname(PROCESSED_PLAYABLE), exist_ok=True)
os.makedirs(os.path.dirname(PROCESSED_NOT_VALID), exist_ok=True)


def fetch_segments(playlist_url, url_chain=None):
    """
    Recursively fetch playlists until reaching segments, then test first reachable segment.
    Returns segment info dict, error message, and full URL chain.
    """
    if url_chain is None:
        url_chain = [playlist_url]

    try:
        r = requests.get(playlist_url, timeout=10)
        r.raise_for_status()
    except Exception as e:
        return None, str(e), url_chain

    try:
        playlist = m3u8.loads(r.text)
    except Exception as e:
        return None, f"Failed to parse m3u8: {e}", url_chain

    # If playlist has variant playlists, follow the first variant
    if playlist.playlists:
        next_url = playlist.playlists[0].absolute_uri
        url_chain.append(next_url)
        return fetch_segments(next_url, url_chain)

    # If playlist has segments, test each until one works
    if playlist.segments:
        for seg in playlist.segments:
            seg_url = seg.absolute_uri
            try:
                start = time.time()
                resp = requests.get(seg_url, timeout=10)
                resp.raise_for_status()
                elapsed = time.time() - start
                return {
                    "segment_url": seg_url,
                    "status": resp.status_code,
                    "bytes": len(resp.content),
                    "elapsed": elapsed
                }, None, url_chain
            except Exception as e:
                continue  # try next segment

    return None, "no valid segments found", url_chain


def main():
    channels = []
    with open(RAW_PLAYLIST, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and not line.endswith(".ctv"):
                channels.append(line)

    playable = []
    not_valid = []

    with open(OUTPUT_CSV, "w", newline="") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=[
                "index",
                "category",
                "reason",
                "url",
                "segment_url",
                "status",
                "bytes",
                "elapsed",
                "error",
                "resolution",
                "url_chain",
            ],
        )
        writer.writeheader()

        for idx, url in enumerate(channels, 1):
            print(f"▶️ [{idx}/{len(channels)}] Checking: {url}")
            segment_info, error, url_chain = fetch_segments(url)

            if segment_info:
                row = {
                    "index": idx,
                    "category": "playable",
                    "reason": "",
                    "url": url,
                    **segment_info,
                    "error": "",
                    "resolution": "",  # optional: could parse resolution from playlist
                    "url_chain": " > ".join(url_chain),
                }
                playable.append(url)
            else:
                row = {
                    "index": idx,
                    "category": "not_valid",
                    "reason": error,
                    "url": url,
                    "segment_url": "",
                    "status": 0,
                    "bytes": 0,
                    "elapsed": 0,
                    "error": error,
                    "resolution": "",
                    "url_chain": " > ".join(url_chain),
                }
                not_valid.append(url)

            writer.writerow(row)

    # Save the filtered playlists
    with open(PROCESSED_PLAYABLE, "w") as f:
        f.write("\n".join(playable))
    with open(PROCESSED_NOT_VALID, "w") as f:
        f.write("\n".join(not_valid))

    print(f"\n✅ Testing complete. Results saved to {OUTPUT_CSV}")
    print(f"Playable channels: {len(playable)}, Not valid channels: {len(not_valid)}")


if __name__ == "__main__":
    main()
