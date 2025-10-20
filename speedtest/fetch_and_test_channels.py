import csv
import re
import requests
from urllib.parse import urljoin

requests.packages.urllib3.disable_warnings()

BITRATE_RESOLUTION_MAP = [
    (2500, "1080p"),
    (1200, "720p"),
    (700, "480p"),
    (400, "360p"),
    (200, "240p"),
]


def extract_resolution_from_text(text):
    match = re.search(r"RESOLUTION=(\d+)x(\d+)", text)
    if match:
        w, h = map(int, match.groups())
        if h >= 1000:
            return "1080p"
        if h >= 700:
            return "720p"
        if h >= 500:
            return "480p"
        if h >= 350:
            return "360p"
        return f"{w}x{h}"
    match = re.search(r"(\d{3,4})[pP](?!\w)", text)
    if match:
        return f"{match.group(1)}p"
    match = re.search(r"(\d{3,4})x(\d{3,4})", text)
    if match:
        w, h = map(int, match.groups())
        if h >= 1000:
            return "1080p"
        if h >= 700:
            return "720p"
        if h >= 500:
            return "480p"
        if h >= 350:
            return "360p"
        return f"{w}x{h}"
    return None


def infer_resolution_from_bitrate(bitrate_kbps):
    for limit, res in BITRATE_RESOLUTION_MAP:
        if bitrate_kbps >= limit:
            return res
    return "low"


def fetch_m3u8(url, depth=0):
    """Recursively fetch .m3u8 until real TS segments are found"""
    try:
        r = requests.get(url, timeout=10, verify=False)
        r.raise_for_status()
        text = r.text
    except Exception as e:
        return None, f"Error fetching {url}: {e}"

    if "#EXTM3U" not in text:
        return None, "Not a valid m3u8"

    # If it's a master playlist with variants
    variant_lines = re.findall(r"#EXT-X-STREAM-INF[^\n]*\n([^\n]+)", text)
    if variant_lines:
        # pick highest resolution or last variant
        last_variant = variant_lines[-1].strip()
        next_url = urljoin(url, last_variant)
        if depth > 3:
            return None, "Too many redirects"
        return fetch_m3u8(next_url, depth + 1)

    return text, None


def probe_first_segment(url):
    """Fetch manifest, pick a TS segment, and probe it."""
    result = {
        "segment_url": "",
        "final_url": url,
        "status": "",
        "bytes": 0,
        "elapsed": 0.0,
        "error": "",
        "encrypted": False,
        "segments_tested": 0,
        "valid_segments": 0,
        "manifest_valid": False,
        "continuity_ok": True,
        "has_extinf": False,
        "avg_segment_duration": 0.0,
        "segment_count": 0,
        "bitrate_kbps": 0.0,
        "resolution": None,
    }

    text, err = fetch_m3u8(url)
    if err:
        result["error"] = err
        return result

    result["manifest_valid"] = True
    result["resolution"] = extract_resolution_from_text(text)

    # check for encryption
    if "#EXT-X-KEY" in text:
        result["encrypted"] = True

    segments = re.findall(r"(?m)^[^#].+\.(ts|m4s|mp4)$", text)
    result["segment_count"] = len(segments)
    if not segments:
        result["error"] = "no valid TS segments"
        return result

    total_bytes = 0
    valid_count = 0
    durations = []

    for seg in segments[:3]:
        seg_url = urljoin(url, seg.strip())
        result["segment_url"] = seg_url
        try:
            r = requests.get(seg_url, timeout=8, stream=True, verify=False)
            result["status"] = r.status_code
            data = r.content[:2048]
            if len(data) > 0 and (data.startswith(b"\x47") or b"ftyp" in data or b"moof" in data):
                valid_count += 1
            total_bytes += len(r.content)
        except Exception as e:
            result["error"] = str(e)
        result["segments_tested"] += 1

    result["valid_segments"] = valid_count
    if valid_count:
        avg_bitrate = (total_bytes * 8 / 1000) / max(1, result["segments_tested"])
        result["bitrate_kbps"] = round(avg_bitrate, 1)

    if not result["resolution"]:
        result["resolution"] = infer_resolution_from_bitrate(result["bitrate_kbps"])

    return result


def analyze_category(row, probe):
    if probe["encrypted"]:
        return "encrypted", "manifest encrypted"
    if not probe["manifest_valid"]:
        return "not_valid", probe["error"]
    if probe["valid_segments"] == 0:
        return "not_valid", probe["error"]
    if probe["bitrate_kbps"] < 150:
        return "low_quality", "low bitrate"
    return "playable", f"{probe['valid_segments']}/{probe['segments_tested']} segments passed"


def main():
    input_file = "input.csv"
    output_file = "output.csv"

    with open(input_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows = list(reader)

    report_rows = []

    for idx, row in enumerate(rows, 1):
        url = row.get("url") or row.get("URL")
        if not url:
            continue

        probe = probe_first_segment(url)
        cat, reason = analyze_category(row, probe)

        report_rows.append({
            "index": idx,
            "category": cat,
            "reason": reason,
            "url": url,
            "segment_url": probe["segment_url"],
            "final_url": probe["final_url"],
            "status": probe["status"],
            "bytes": probe["bytes"],
            "elapsed": probe["elapsed"],
            "error": probe["error"],
            "encrypted": probe["encrypted"],
            "segments_tested": probe["segments_tested"],
            "valid_segments": probe["valid_segments"],
            "manifest_valid": probe["manifest_valid"],
            "continuity_ok": probe["continuity_ok"],
            "has_extinf": probe["has_extinf"],
            "avg_segment_duration": probe["avg_segment_duration"],
            "segment_count": probe["segment_count"],
            "bitrate_kbps": probe["bitrate_kbps"],
            "resolution": probe["resolution"],
        })

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=report_rows[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"✅ Done. {len(report_rows)} channels analyzed → {output_file}")


if __name__ == "__main__":
    main()
