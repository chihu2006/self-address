import requests
from urllib.parse import urljoin

def test_m3u8_playable(m3u8_url):
    try:
        # Step 1: Fetch the m3u8 playlist
        response = requests.get(m3u8_url, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch playlist: {response.status_code}")
            return False

        content = response.text
        if not content.startswith("#EXTM3U"):
            print("Invalid m3u8 content")
            return False

        # Step 2: Find the first segment
        lines = content.splitlines()
        first_segment = None
        for i, line in enumerate(lines):
            if line.strip() and not line.startswith("#"):
                first_segment = line.strip()
                break

        if not first_segment:
            print("No media segments found in playlist")
            return False

        # Handle relative URLs
        first_segment_url = urljoin(m3u8_url, first_segment)

        # Step 3: Fetch the first segment
        seg_resp = requests.get(first_segment_url, timeout=10, stream=True)
        if seg_resp.status_code == 200 and seg_resp.content:
            print(f"Playable! First segment fetched: {first_segment_url}")
            return True
        else:
            print(f"Failed to fetch first segment: {seg_resp.status_code}")
            return False

    except requests.RequestException as e:
        print(f"Error fetching playlist or segment: {e}")
        return False

# Example usage:
channel_url = "https://example.com/live/stream.m3u8"
test_m3u8_playable(channel_url)
