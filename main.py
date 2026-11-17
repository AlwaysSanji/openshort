import sys
import time
import webbrowser
import threading
import uvicorn
from app.config import config

def open_browser_delayed(url: str, delay: float = 1.2):
    time.sleep(delay)
    print(f"[Launcher] Opening browser: {url}")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"[Launcher] Could not open browser automatically: {e}")

def main():
    port = config.port
    url = f"http://localhost:{port}"

    print("=" * 65)
    print(" ⚡ OpenShort LiveClipper - Automated PC Highlight Clipper")
    print(f" 🌐 Dashboard URL: {url}")
    print(" ⌨️  Global Hotkey: Press [F9] anywhere on PC to instant-clip")
    print("=" * 65)

    # Launch browser in a background thread
    threading.Thread(target=open_browser_delayed, args=(url,), daemon=True).start()

    # Start FastAPI server
    try:
        uvicorn.run(
            "server:app",
            host="127.0.0.1",
            port=port,
            log_level="info",
            access_log=False
        )
    except KeyboardInterrupt:
        print("\n[Launcher] Shutting down OpenShort LiveClipper...")

if __name__ == "__main__":
    main()
