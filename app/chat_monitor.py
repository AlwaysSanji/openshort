import socket
import threading
import time
import re
from collections import deque
from typing import Dict, Optional

HYPE_WORDS = {
    "pog", "poggers", "omegalul", "lmao", "lol", "wtf", "omg", "w",
    "insane", "clip", "clip it", "lets go", "sheesh", "clutch", "holy",
    "dead", "nahhh", "gg", "w streamer", "gigachad", "pepega", "monkas"
}

class TwitchChatMonitor:
    """
    Connects to Twitch IRC anonymously (no credentials required)
    to monitor chat velocity and hype buzzwords in real-time.
    """
    def __init__(self):
        self.channel: Optional[str] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.recent_messages = deque(maxlen=200) # (timestamp, text)
        self.lock = threading.Lock()
        self.msg_rate = 0.0
        self.chat_score = 0.0

    def start(self, channel_or_url: str):
        # Extract channel name from URL if needed
        channel = channel_or_url.strip().lower()
        if "twitch.tv/" in channel:
            channel = channel.split("twitch.tv/")[-1].split("/")[0].split("?")[0]
        channel = channel.lstrip("#")
        if not channel:
            return

        self.stop()
        self.channel = channel
        self._running = True
        self.recent_messages.clear()
        self._thread = threading.Thread(target=self._irc_worker, daemon=True)
        self._thread.start()
        print(f"[ChatMonitor] Listening to Twitch chat: #{self.channel}")

    def stop(self):
        self._running = False
        self.channel = None
        with self.lock:
            self.recent_messages.clear()
            self.msg_rate = 0.0
            self.chat_score = 0.0

    def get_stats(self) -> Dict[str, float]:
        with self.lock:
            now = time.time()
            # Clean messages older than 10 seconds
            while self.recent_messages and (now - self.recent_messages[0][0]) > 10.0:
                self.recent_messages.popleft()

            msg_count = len(self.recent_messages)
            self.msg_rate = round(msg_count / 10.0, 1) # msgs per second

            # Count hype keywords
            hype_count = 0
            for _, text in self.recent_messages:
                lower = text.lower()
                for word in HYPE_WORDS:
                    if word in lower:
                        hype_count += 1

            # Normal stream: 0-3 msg/s. Crazy hype moment: 15-40+ msg/s with lots of emotes
            # Map msg_rate to 0-60 points, hype_count to 0-40 points
            rate_score = min(60.0, (self.msg_rate / 15.0) * 60.0)
            hype_score = min(40.0, (hype_count / 10.0) * 40.0)
            self.chat_score = round(rate_score + hype_score, 1)

            return {
                "msg_rate": self.msg_rate,
                "chat_score": self.chat_score,
                "channel": self.channel or ""
            }

    def _irc_worker(self):
        server = "irc.chat.twitch.tv"
        port = 6667
        nickname = "justinfan12891" # Standard Twitch anonymous guest user

        while self._running and self.channel:
            try:
                sock = socket.socket()
                sock.settimeout(10.0)
                sock.connect((server, port))
                sock.send(f"PASS SCHMOOPIIE\r\n".encode("utf-8"))
                sock.send(f"NICK {nickname}\r\n".encode("utf-8"))
                sock.send(f"JOIN #{self.channel}\r\n".encode("utf-8"))

                buffer = ""
                while self._running:
                    try:
                        data = sock.recv(2048).decode("utf-8", errors="ignore")
                        if not data:
                            break
                        buffer += data
                        lines = buffer.split("\r\n")
                        buffer = lines.pop()

                        for line in lines:
                            if line.startswith("PING"):
                                sock.send("PONG :tmi.twitch.tv\r\n".encode("utf-8"))
                            elif "PRIVMSG" in line:
                                parts = line.split(":", 2)
                                if len(parts) >= 3:
                                    msg_text = parts[2]
                                    with self.lock:
                                        self.recent_messages.append((time.time(), msg_text))
                    except socket.timeout:
                        continue
                    except Exception:
                        break
                sock.close()
            except Exception as e:
                time.sleep(3)

chat_monitor = TwitchChatMonitor()
