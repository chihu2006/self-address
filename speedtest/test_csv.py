#!/usr/bin/env python3
import csv
import requests

CTV_FILE = "rawaddress/freetv_ctv.m3u"
OUTPUT_FILE = "speedtest/ctv_test_result.csv"

urls = []
with open(CTV_FILE, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)

results = []

for url in urls:
    try:
        r = requests.get(url, allow_redirects=True, timeout=10)
        final_url = r.url
        status = r.status_code
    except Exception as e:
        final_url = ""
        status = ""
        print(f"Error fetching {url}: {e}")

    results.append({"original_url": url, "final_url": final_url, "status": status})

# Write CSV
import os
os.makedirs("speedtest", exist_ok=True)
with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["original_url", "final_url", "status"])
    writer.writeheader()
    writer.writerows(results)

print(f"✅ .ctv test result saved to {OUTPUT_FILE}")
