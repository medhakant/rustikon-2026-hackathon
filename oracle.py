import requests

class OracleClient:
    def __init__(self, host: str, token: str, port: int = 50051):
        self.url = f"http://{host}:{port}/quadrant"
        self.headers = {"Authorization": token}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
    def get_target_quadrant(self):
        try:
            resp = self.session.get(self.url, timeout=1.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("quadrant", None)
            else:
                print(f"[Oracle] HTTP Error: {resp.status_code} - {resp.text}")
                return None
        except Exception as e:
            print(f"[Oracle] Exception: {e}")
            return None
