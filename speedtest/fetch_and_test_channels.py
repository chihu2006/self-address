import csv
import requests

# Path to the M3U file
M3U_FILE = "rawaddress/freetv.m3u"
OUTPUT_CSV = "rawaddress/validation_result.csv"

# Step 1: Read M3U file
channels = []
with open(M3U_FILE, "r", encoding="utf-8") as f:
    lines = f.readlines()
    for i in range(len(lines)):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            info = line
            url = lines[i+1].strip()
            channels.append({"info": info, "url": url})

# Step 2: Select channels
print(f"Total channels found: {len(channels)}")
selection = input("Enter channel numbers/range to validate (e.g., 1-50 or 1,3,5): ")

# Parse selection
selected_channels = []
if "-" in selection:
    start, end = map(int, selection.split("-"))
    selected_channels = channels[start-1:end]
else:
    indices = [int(x)-1 for x in selection.split(",")]
    selected_channels = [channels[i] for i in indices]

# Step 3: Validate each channel
results = []
for ch in selected_channels:
    url = ch["url"]
    try:
        r = requests.head(url, timeout=5)
        status = r.status_code
    except Exception as e:
        status = f"ERROR: {e}"
    results.append({"info": ch["info"], "url": url, "status": status})

# Step 4: Save to CSV
with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["info", "url", "status"])
    writer.writeheader()
    for row in results:
        writer.writerow(row)

print(f"Validation complete! Results saved to {OUTPUT_CSV}")
