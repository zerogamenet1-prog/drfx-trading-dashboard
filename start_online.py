import os
import re
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLOUDFLARED = os.path.join(BASE_DIR, "cloudflared.exe")

print("=" * 60)
print("🚀 LAUNCHING DRFX LIVE TRADING DASHBOARD ONLINE...")
print("=" * 60)

# 1. Start FastAPI Uvicorn Server in background
server_process = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8000", "--reload"],
    cwd=BASE_DIR,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)
print("✅ Local Server started on http://127.0.0.1:8000")
time.sleep(2)

# 2. Start Cloudflare Tunnel
print("🌐 Connecting to Cloudflare Global Network for Public HTTPS...")
cf_process = subprocess.Popen(
    [CLOUDFLARED, "tunnel", "--url", "http://127.0.0.1:8000"],
    cwd=BASE_DIR,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)

public_url = None
start_time = time.time()

# Read lines from cloudflared until we find the trycloudflare.com URL
while time.time() - start_time < 30:
    line = cf_process.stdout.readline()
    if not line:
        time.sleep(0.1)
        continue
    # Look for trycloudflare.com URL
    match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
    if match:
        public_url = match.group(0)
        break

if public_url:
    print("\n" + "=" * 60)
    print(f"🎉 DASHBOARD IS NOW LIVE ON THE INTERNET!")
    print(f"🌐 Public Web URL   : {public_url}")
    print(f"📡 MT5 Report URL   : {public_url}/api/report")
    print("=" * 60 + "\n")

    # Save to file
    with open(os.path.join(BASE_DIR, "public_url.txt"), "w") as f:
        f.write(public_url)
else:
    print("⚠️ Could not capture public URL within 30 seconds.")

# Keep running
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping services...")
    server_process.terminate()
    cf_process.terminate()

