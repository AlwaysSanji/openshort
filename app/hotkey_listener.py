import threading
from typing import Optional
from app.config import config

class GlobalHotkeyManager:
    """
    Listens for global PC hotkeys (e.g. F9) to trigger instant retrospective clips.
    Works anywhere on the PC (in games, browser, desktop).
    """
    def __init__(self):
        self._listener = None
        self._callback = None
        self.is_running = False

    def start(self, on_trigger):
        self._callback = on_trigger
        try:
            from pynput import keyboard

            def on_press(key):
                try:
                    # Check for F9 key
                    if key == keyboard.Key.f9:
                        print("[Hotkey] F9 pressed -> Triggering clip!")
                        if self._callback:
                            self._callback("Manual Hotkey (F9)")
                except Exception as e:
                    print(f"[Hotkey] Error handling key press: {e}")

            self._listener = keyboard.Listener(on_press=on_press)
            self._listener.daemon = True
            self._listener.start()
            self.is_running = True
            print(f"[Hotkey] Global hotkey listener active (Press F9 to clip).")
        except Exception as e:
            print(f"[Hotkey] Global hotkey hook not available in this environment: {e}")

    def stop(self):
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        self.is_running = False

hotkey_manager = GlobalHotkeyManager()
