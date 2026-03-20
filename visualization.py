import threading
import time
import cv2
import numpy as np
from flask import Flask, Response, render_template_string
from flask_cors import CORS

class VisualizationServer:
    def __init__(self, host="0.0.0.0", port=5001):
        self.app = Flask(__name__)
        CORS(self.app)
        self.host = host
        self.port = port
        
        # State to be shared between the main controller and the web server
        self.lock = threading.Lock()
        self.frame = None
        self.field_state = {
            "car_pos": [0.5, 0.5],
            "car_heading": 0.0,
            "target_q": None,
            "corners": [[0,0], [1,0], [1,1], [0,1]]
        }
        
        self._setup_routes()
        self.thread = threading.Thread(target=self._run, daemon=True)
        
    def _setup_routes(self):
        @self.app.route('/')
        def index():
            return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Car Control Dashboard</title>
    <style>
        body { font-family: sans-serif; background: #121212; color: white; display: flex; flex-direction: column; align-items: center; }
        .container { display: flex; gap: 20px; padding: 20px; flex-wrap: wrap; justify-content: center; }
        .view-box { background: #1e1e1e; padding: 10px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        h2 { margin-top: 0; color: #bb86fc; }
        #field-canvas { background: #2c2c2c; border: 2px solid #3d3d3d; }
        .controls { margin-top: 10px; font-size: 0.9em; color: #aaa; }
    </style>
</head>
<body>
    <h1>Rustikon 2026: Visualization</h1>
    <div class="container">
        <div class="view-box">
            <h2>Live Feed</h2>
            <img src="/video_feed" width="640" height="480" style="border-radius: 4px;">
        </div>
        <div class="view-box">
            <h2>Field Representation</h2>
            <canvas id="field-canvas" width="480" height="480"></canvas>
            <div id="status" class="controls">
                Initializing field...
            </div>
        </div>
    </div>

    <script>
        const canvas = document.getElementById('field-canvas');
        const ctx = canvas.getContext('2d');
        const size = 480;
        const margin = 40;
        const innerSize = size - 2 * margin;

        function toCanvas(x, y) {
            // Mapping [0,1] to [margin, margin + innerSize]
            // Note: y is inverted if we want Cartesian (0,0 at bottom-left)
            return {
                x: margin + x * innerSize,
                y: margin + (1 - y) * innerSize
            };
        }

        async function updateState() {
            try {
                const response = await fetch('/state');
                const state = await response.json();
                
                // Clear
                ctx.clearRect(0, 0, size, size);
                
                // Draw Grid
                ctx.strokeStyle = '#333';
                ctx.beginPath();
                for(let i=0; i<=4; i++) {
                    const p1 = toCanvas(i/4, 0);
                    const p2 = toCanvas(i/4, 1);
                    ctx.moveTo(p1.x, p1.y);
                    ctx.lineTo(p2.x, p2.y);
                    const p3 = toCanvas(0, i/4);
                    const p4 = toCanvas(1, i/4);
                    ctx.moveTo(p3.x, p3.y);
                    ctx.lineTo(p4.x, p4.y);
                }
                ctx.stroke();

                // Draw Field Boundary
                ctx.strokeStyle = '#03dac6';
                ctx.lineWidth = 2;
                ctx.strokeRect(margin, margin, innerSize, innerSize);

                // Draw Quadrants
                ctx.fillStyle = 'rgba(255, 255, 255, 0.05)';
                if (state.target_q) {
                    let qx = 0, qy = 0;
                    if (state.target_q === 1) { qx = 0.5; qy = 0.5; }
                    if (state.target_q === 2) { qx = 0; qy = 0.5; }
                    if (state.target_q === 3) { qx = 0; qy = 0; }
                    if (state.target_q === 4) { qx = 0.5; qy = 0; }
                    const p = toCanvas(qx, qy + 0.5);
                    ctx.fillRect(p.x, p.y, innerSize/2, innerSize/2);
                    ctx.fillStyle = '#cf6679';
                    ctx.fillText("TARGET Q" + state.target_q, p.x + 10, p.y + 20);
                }

                // Draw Car
                const car = toCanvas(state.car_pos[0], state.car_pos[1]);
                ctx.save();
                ctx.translate(car.x, car.y);
                ctx.rotate(-state.car_heading); // Negative because canvas Y is down

                // Car body
                ctx.fillStyle = '#bb86fc';
                ctx.beginPath();
                ctx.moveTo(15, 0);
                ctx.lineTo(-10, -8);
                ctx.lineTo(-10, 8);
                ctx.closePath();
                ctx.fill();
                
                // Direction arrow
                ctx.strokeStyle = 'white';
                ctx.beginPath();
                ctx.moveTo(0,0);
                ctx.lineTo(20, 0);
                ctx.stroke();
                
                ctx.restore();

                document.getElementById('status').innerText = 
                    `Pos: (${state.car_pos[0].toFixed(2)}, ${state.car_pos[1].toFixed(2)}) | Heading: ${((state.car_heading * 180 / Math.PI)).toFixed(1)}°`;

            } catch (e) { console.error(e); }
        }

        setInterval(updateState, 100);
    </script>
</body>
</html>
            """)

        @self.app.route('/video_feed')
        def video_feed():
            return Response(self._generate_frames(),
                            mimetype='multipart/x-mixed-replace; boundary=frame')

        @self.app.route('/state')
        def get_state():
            with self.lock:
                return self.field_state

    def _generate_frames(self):
        while True:
            with self.lock:
                if self.frame is None:
                    time.sleep(0.05)
                    continue
                ret, buffer = cv2.imencode('.jpg', self.frame)
                frame_bytes = buffer.tobytes()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.05)

    def update(self, frame, car_pos=None, car_heading=None, target_q=None):
        with self.lock:
            if frame is not None:
                self.frame = frame
            if car_pos is not None:
                self.field_state["car_pos"] = [float(car_pos[0]), float(car_pos[1])]
            if car_heading is not None:
                self.field_state["car_heading"] = float(car_heading)
            if target_q is not None:
                self.field_state["target_q"] = target_q

    def _run(self):
        # Disable logging to avoid spamming the console
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        self.app.run(host=self.host, port=self.port, threaded=True, use_reloader=False)

    def start(self):
        self.thread.start()
        print(f"Visualization server started at http://{self.host}:{self.port}")
