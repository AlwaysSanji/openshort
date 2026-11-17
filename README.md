# ⚡ OpenShort LiveClipper

<p align="center">
  <strong>Autonomous AI-Powered Highlight Clipper for Live Streams & PC Gameplay</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/FFmpeg-Enabled-green?logo=ffmpeg&logoColor=white" alt="FFmpeg" />
  <img src="https://img.shields.io/badge/AI-Faster--Whisper-purple" alt="Faster-Whisper" />
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white" alt="Windows" />
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="License" />
</p>

---

## 📌 Overview

**OpenShort LiveClipper** is an autonomous clipping station built for content creators and streamers. It continuously monitors live streams or local PC desktop gameplay inside a zero-latency circular buffer, automatically identifies high-energy moments (caster hype, screams, chat bursts, combat peaks), and instantly cuts lossless 16:9 highlight clips and viral 9:16 vertical shorts.

---

## 🚀 Key Highlights

### 🧠 1. Multi-Signal Excitement Engine
- **Audio Surge & Scream Detection**: Calculates dynamic decibel energy (dBFS) and rolling Z-score standard deviations to catch sudden shouts, cheers, and explosions while ignoring steady background music.
- **Visual Motion Dynamics**: Computes frame-to-frame optical differentials at 30 fps to detect rapid camera pans, explosions, and combat action.
- **Twitch Chat Velocity Tracker**: Connects anonymously to Twitch IRC (`irc.chat.twitch.tv`) to detect message rate surges and hype emotes (`POG`, `LMAO`, `WTF`, `W`, `CLIP IT`, `INSANE`).
- **Global Hotkey (`F9`)**: Retroactively extracts the last 30 seconds anytime from full-screen games or desktop applications.

### 🔄 2. Circular Rolling Buffer
- Keeps a lightweight 60–120 second segmented memory cache.
- Cuts exact windows: `[Event - PreRoll]` to `[Event + PostRoll]`.
- Automatically debounces back-to-back excitement bursts to prevent chopped duplicates.

### 📱 3. Studio Pro Shorts Suite
- **🌟 Studio Ambient Glow**: 1080x1920 layout with dimmed, blurred background depth and centered sharp gameplay.
- **🎮 Stacked Split**: Top 35% zoomed facecam with bottom 65% gameplay action (the standard for TikTok and YouTube Shorts).
- **🎯 Action Zoom**: Full 1080x1920 borderless action focus.
- **🔊 EBU R128 Broadcast Audio Leveling**: Built-in `loudnorm` filter eliminates distorted screaming while elevating soft speech.
- **🎨 HDR Color Grade**: Enhances contrast (+8%) and saturation (+18%) for high-impact visual pop.
- **🔥 AI Styled Captions**: Automatically generates and burns in bold yellow, black-bordered viral subtitles via local `faster-whisper`.

### 🔗 4. Universal Link Clipper
- Paste any YouTube video, YouTube Live stream, Twitch VOD, or Kick URL.
- Auto-detects highlights or cuts custom time intervals without downloading entire streams.

---

## 🛠️ Architecture

```
                  ┌──────────────────────────────┐
                  │ Ingestion Sources            │
                  │ • Live URL (Twitch/YouTube)  │
                  │ • PC Desktop (gdigrab)       │
                  │ • Local Video / VOD          │
                  │ • Synthetic Live Simulator   │
                  └──────────────┬───────────────┘
                                 │
                                 ▼
                  ┌──────────────────────────────┐
                  │ Rolling Ring Buffer (120s)   │
                  └──────────────┬───────────────┘
                                 │
                     ┌───────────┴───────────┐
                     ▼                       ▼
          ┌──────────────────────┐  ┌──────────────────┐
          │ Excitement Engine    │  │ Global PC Hotkey │
          │ • Audio dBFS Surge   │  │ • F9 Listener    │
          │ • Motion Dynamics    │  └────────┬─────────┘
          │ • Chat Velocity      │           │
          └──────────┬───────────┘           │
                     │                       │
                     └───────────┬───────────┘
                                 │ Trigger Event
                                 ▼
                  ┌──────────────────────────────┐
                  │ Clip Extraction & Concat     │
                  └──────────────┬───────────────┘
                                 │
                     ┌───────────┴───────────┐
                     ▼                       ▼
          ┌──────────────────────┐  ┌──────────────────┐
          │ 16:9 Lossless Master │  │ Studio Pro 9:16  │
          │ • HDR Color Grade    │  │ • Ambient Glow   │
          │ • Loudnorm Audio     │  │ • Stacked Split  │
          │ • Smooth Fades       │  │ • Action Zoom    │
          └──────────────────────┘  │ • Viral Captions │
                                    └──────────────────┘
```

---

## 💻 Quick Start

### Prerequisites
1. **Python 3.10+** installed.
2. **FFmpeg** installed and accessible in your system `PATH`.

### Installation
```bash
git clone https://github.com/AlwaysSanji/openshort.git
cd openshort
pip install -r requirements.txt
```

### Launching the Dashboard
- **Windows 1-Click**: Double-click `start.bat`
- **Or via Terminal**:
  ```bash
  python main.py
  ```
The dashboard will open automatically in your browser at:  
👉 **`http://localhost:8000`**

---

## ⌨️ Controls & Shortcuts

| Action | Shortcut / Control |
|---|---|
| **Instant Clip** | Press `F9` anywhere on PC (desktop or in-game) |
| **Play / Pause Clip** | `Spacebar` in player modal |
| **Direct URL Clipping** | Navigate to `🔗 Clip From Link` tab in dashboard |
| **Tuning Settings** | Click `⚙️` to adjust thresholds & buffer windows |

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/status` | Read ingestion engine & buffer status |
| `POST` | `/api/start` | Start live capture (`url`, `desktop`, `simulator`) |
| `POST` | `/api/stop` | Stop live capture |
| `POST` | `/api/clip_now` | Trigger instantaneous retroactive clip |
| `POST` | `/api/clip_from_link` | Extract clip from YouTube/Twitch link |
| `GET` | `/api/clips` | Fetch all saved clips & metadata |
| `POST` | `/api/clips/{id}/short` | Generate 9:16 vertical short (`studio_glow`, `stacked_split`) |
| `POST` | `/api/clips/{id}/enhance` | Remaster 16:9 clip with loudnorm & color grade |
| `POST` | `/api/clips/{id}/trim` | Trim clip with custom start and end points |
| `POST` | `/api/clips/{id}/open` | Reveal file in Windows File Explorer |
| `DELETE` | `/api/clips/{id}` | Delete clip and associated files |

---

## 📄 License
This project is open-source under the [MIT License](LICENSE).
