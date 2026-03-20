import requests
import numpy as np
import cv2
import time
import os

class CameraClient:
    def __init__(self, host: str, token: str, port: int = 50051):
        self.host = host
        self.url = f"http://{host}:{port}/frame"
        self.headers = {"Authorization": token}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.last_fetch_time = 0
        self.interval = 0.1 # 100ms
        self.save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp")
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
        
    def get_frame(self):
        now = time.time()
        if now - self.last_fetch_time < self.interval:
            # We already have a frame or it's too early. 
            # In a real control loop, we might want to return the cached frame or None.
            return None
        
        try:
            resp = self.session.get(self.url, timeout=1.0)
            self.last_fetch_time = time.time() 
            if resp.status_code == 200:
                # Save first for debugging as requested
                timestamp = int(self.last_fetch_time * 1000)
                # file_path = os.path.join(self.save_dir, f"cam_{self.host}_{timestamp}.png")
                # with open(file_path, "wb") as f:
                #     f.write(resp.content)
                
                image_array = np.asarray(bytearray(resp.content), dtype=np.uint8)
                frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
                return frame
            else:
                print(f"[Camera {self.url}] HTTP Error: {resp.status_code}")
                return None
        except Exception as e:
            print(f"[Camera {self.url}] Exception: {e}")
            return None
