import requests
import numpy as np
import cv2

class CameraClient:
    def __init__(self, host: str, token: str, port: int = 50051):
        self.url = f"http://{host}:{port}/frame"
        self.headers = {"Authorization": token}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
    def get_frame(self):
        try:
            resp = self.session.get(self.url, timeout=1.0)
            if resp.status_code == 200:
                image_array = np.asarray(bytearray(resp.content), dtype=np.uint8)
                frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
                return frame
            else:
                print(f"[Camera {self.url}] HTTP Error: {resp.status_code}")
                return None
        except Exception as e:
            print(f"[Camera {self.url}] Exception: {e}")
            return None
