import requests

def is_playable(m3u8_url):
    try:
        # Fetch the .m3u8 playlist
        resp = requests.get(m3u8_url, timeout=10)
        if resp.status_code != 200:
            return False
        
        lines = resp.text.splitlines()
        # Find the first segment URL (skip lines starting with #)
        segment_url = None
        for line in lines:
            if line and not line.startswith('#'):
                segment_url = line
                break
        
        if not segment_url:
            return False
        
        # Make the segment URL absolute if needed
        if not segment_url.startswith('http'):
            if m3u8_url.endswith('/'):
                segment_url = m3u8_url + segment_url
            else:
                segment_url = '/'.join(m3u8_url.split('/')[:-1]) + '/' + segment_url
        
        # Test the first segment
        seg_resp = requests.get(segment_url, timeout=10)
        return seg_resp.status_code == 200
    except Exception:
        return False

# Example usage
final_m3u8_url = "https://example.com/stream/playlist.m3u8"
if is_playable(final_m3u8_url):
    print("Playable ✅")
else:
    print("Not playable ❌")
