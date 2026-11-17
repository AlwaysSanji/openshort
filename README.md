# ⚡ OpenShort LiveClipper

**OpenShort LiveClipper** is an autonomous clipping station for PC that monitors live streams or local gameplay in real time, automatically detects the best moments (screams, caster hype, crazy kills, chat explosions, explosive action), and instantly extracts lossless clips and viral 9:16 vertical shorts.

---

## 🌟 Key Features

1. **Multi-Signal "Best Part" Excitement Engine**:
   - 🔊 **Audio Surge & Screaming Detection**: Tracks dynamic decibels (dBFS) and Z-score variance against ambient stream noise. Triggers on screams, caster hype, laughs, and sudden loud volume surges.
   - 🎬 **Visual Motion Dynamics**: Optical frame-difference analysis detecting rapid combat, camera whips, screen flashes, and high-action sequences.
   - 💬 **Live Twitch Chat Velocity & Buzzwords**: Reads Twitch chat anonymously (`irc.chat.twitch.tv`) in real-time, detecting message rate spikes and hype emotes (`POG`, `POGGERS`, `OMEGALUL`, `LMAO`, `WTF`, `W`, `CLIP IT`, `INSANE`).
   - ⚡ **Global PC Hotkey (`F9`)**: Hit `F9` anywhere on your PC (even inside full-screen games) to retroactively save the last 30 seconds into your clips library!

2. **Circular Rolling Ring-Buffer (Zero Lag)**:
   - Maintains a smooth rolling buffer of the past 60–120 seconds in micro-segments.
   - When a highlight is triggered, it extracts `[Trigger - PreRoll]` to `[Trigger + PostRoll]` (e.g. 15s before the spike + 10s after).
   - Automatically debounces and merges continuous hype moments into coherent single clips.

3. **Multiple Ingestion Sources**:
   - 🌐 **Live Stream URL**: Ingest live streams from **Twitch, YouTube Live, Kick**, or direct HLS/m3u8/RTMP links.
   - 🖥️ **PC Desktop / Game Capture**: Ingest your desktop screen & game live via FFmpeg.
   - 📁 **Local Video / VOD**: Fast-scan pre-recorded videos to auto-generate highlights.
   - 🎮 **Live Demo Simulator**: Built-in test simulator with periodic hype moments to test the entire clipping pipeline with 1 click!

4. **1-Click 9:16 Shorts & TikTok Converter**:
   - Transforms 16:9 widescreen highlights into 1080x1920 9:16 vertical shorts.
   - Features ambient blurred background framing (the standard used by top creators) or direct center cropping.

5. **AI Subtitles with Faster-Whisper**:
   - Built-in speech recognition generates word-level `.srt` subtitles automatically for your clips.

6. **Cyberpunk Creator Dashboard**:
   - Real-time animated radial excitement gauge (0-100%).
   - Live audio decibel meters & motion trackers.
   - Interactive clip gallery with built-in HTML5 player, trimmer, download, and "Show in Windows Explorer" integration.

---

## 🚀 Quick Start (Windows PC)

### 1-Click Launch:
Double-click `start.bat` in the project folder.

### Or via Terminal:
```bash
python main.py
```
This automatically launches the application and opens your default browser to:
👉 **`http://localhost:8000`**

---

## ⌨️ Hotkeys & Controls

| Shortcut | Action |
|---|---|
| **F9** | Global PC Hotkey: Instantly saves the last 30 seconds from anywhere (in-game or desktop) |
| **Space** | Play / Pause clip in modal player |
| **Settings (⚙️)** | Adjust excitement thresholds, pre/post roll durations, and signal weights |

---

## 📁 Project Structure

```
openshort/
├── app/
│   ├── buffer_manager.py     # Thread-safe rolling ring buffer
│   ├── chat_monitor.py       # Anonymous Twitch IRC chat velocity monitor
│   ├── clipper.py            # FFmpeg clip extractor, 9:16 short converter & metadata
│   ├── config.py             # Settings & persistence
│   ├── detector.py           # Multi-signal excitement detection engine
│   ├── hotkey_listener.py    # Global PC keyboard hook (pynput)
│   ├── stream_ingest.py      # Multi-source live ingestion manager
│   └── transcriber.py        # faster-whisper AI subtitle generator
├── static/
│   ├── app.js               # Reactive WebSocket UI logic
│   ├── index.html            # Dark cyberpunk dashboard UI
│   ├── style.css             # Glassmorphism & animated styling
│   └── thumb_fallback.png    # Fallback clip thumbnail
├── clips/                    # Exported highlight MP4s, shorts, and thumbnails
├── temp_buffer/              # Temporary circular buffer cache
├── server.py                 # FastAPI backend & WebSocket server
├── main.py                   # PC CLI / Desktop launcher
├── start.bat                 # 1-Click Windows launcher
├── test_system.py            # End-to-end automated verification tests
└── README.md                 # Documentation
```

---

## 🛠️ REST API Endpoints

- `GET /api/status` - Current streaming and buffer status
- `POST /api/start` - Start monitoring (`{"source_type": "simulator|url|desktop|file", "source_target": "..."}`)
- `POST /api/stop` - Stop monitoring
- `POST /api/clip_now` - Trigger retroactive clip
- `GET /api/clips` - Get all captured clips with metadata
- `POST /api/clips/{id}/short` - Convert clip to 9:16 vertical short
- `POST /api/clips/{id}/trim` - Trim clip with `{start_time, end_time}`
- `POST /api/clips/{id}/transcribe` - Generate subtitles with Whisper AI
- `POST /api/clips/{id}/open` - Reveal clip in Windows File Explorer
- `DELETE /api/clips/{id}` - Delete clip and associated files
- `GET /api/config` & `POST /api/config` - Read / update thresholds
