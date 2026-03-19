import threading
import time
import requests

class CarClient:
    def __init__(self, host: str, token: str, port: int = 50051):
        self.url = f"http://{host}:{port}/"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": token
        }
        
        self._speed = 0.0
        self._flip = False
        
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

    def set_command(self, speed: float, flip: bool, enforce_deadband: bool = True):
        with self._lock:
            # Enforce 0.35 deadband if requested and moving
            if enforce_deadband and speed != 0.0:
                if 0 < speed < 0.35:
                    speed = 0.35
                elif -0.35 < speed < 0:
                    speed = -0.35
            
            # Constrain to valid range
            self._speed = max(-1.0, min(1.0, float(speed)))
            self._flip = bool(flip)

    def stop_car(self):
        self.set_command(0.0, False, enforce_deadband=False)

    def _heartbeat_loop(self):
        # Use session to reuse TCP connections if possible (though the hackathon server might drop them)
        session = requests.Session()
        session.headers.update(self.headers)
        
        while self._running:
            with self._lock:
                speed = self._speed
                flip = self._flip
                
            payload = {
                "speed": speed,
                "flip": flip
            }
            try:
                # 100ms cooldown: timeout ensures the loop doesn't block too long
                session.put(self.url, json=payload, timeout=0.08)
            except requests.exceptions.Timeout:
                # Expected if we set timeout very low to keep 10Hz pace
                pass
            except Exception:
                pass
            
            time.sleep(0.1)

    def start_heartbeat(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._thread.start()
            print("[CarClient] Heartbeat started.")

    def stop_heartbeat(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        self.stop_car()
        print("[CarClient] Heartbeat stopped.")
