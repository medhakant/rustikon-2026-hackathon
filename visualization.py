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
        self.frame1 = None
        self.frame2 = None
        self.field_state = {
            "car_pos": [0.5, 0.5],
            "car_heading": 0.0,
            "target_q": None,
            "corners": [11, 12, 13, 14] # Corner IDs
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
        body { font-family: 'Inter', sans-serif; background: #0f0f0f; color: #e0e0e0; margin: 0; padding: 0; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
        header { background: #1a1a1a; padding: 10px 30px; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;}
        h1 { margin: 0; font-size: 1.2em; color: #03dac6; letter-spacing: 1px; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; gap: 10px; padding: 10px; flex-grow: 1; min-height: 0; }
        .quadrant { background: #181818; border-radius: 8px; border: 1px solid #333; position: relative; overflow: hidden; display: flex; flex-direction: column; min-height: 0; }
        .quadrant-title { position: absolute; top: 10px; left: 10px; background: rgba(0,0,0,0.7); padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 0.75em; color: #bb86fc; z-index: 10; border: 1px solid #444; }
        .right-half { grid-column: 2 / 3; grid-row: 1 / 3; }
        .camera-feed { width: 100%; height: 100%; object-fit: contain; background: #000; }
        canvas { width: 100%; height: 100%; }
        #status-bar { background: #1a1a1a; padding: 8px 30px; border-top: 1px solid #333; font-size: 0.85em; color: #999; display: flex; gap: 20px; flex-shrink: 0; }
        .highlight { color: #03dac6; font-weight: bold; }
        #debug-controls button {
            background: #333; color: #fff; border: 1px solid #444; padding: 2px 8px; 
            border-radius: 3px; cursor: pointer; font-size: 0.8em; font-family: inherit;
        }
        #debug-controls button:hover { background: #444; }
    </style>
</head>
<body>
    <header>
        <h1>RUSTIKON 2026 :: CAR CONTROL</h1>
        <div style="display: flex; gap: 10px; align-items: center;">
            <div id="debug-controls" style="background: #222; padding: 5px; border-radius: 4px; display: flex; gap: 5px;">
                <span style="font-size: 0.7em; margin-right: 5px; color: #777;">SET TARGET:</span>
                <button onclick="setTarget(1)">Q1</button>
                <button onclick="setTarget(2)">Q2</button>
                <button onclick="setTarget(3)">Q3</button>
                <button onclick="setTarget(4)">Q4</button>
                <button onclick="setTarget(11)" style="color:#03dac6">C11</button>
                <button onclick="setTarget(12)" style="color:#03dac6">C12</button>
                <button onclick="setTarget(13)" style="color:#03dac6">C13</button>
                <button onclick="setTarget(14)" style="color:#03dac6">C14</button>
                <button onclick="setTarget(0)" style="color:#aaa">Auto</button>
            </div>
            <div id="live-indicator"><span class="highlight">●</span> LIVE</div>
        </div>
    </header>
    
    <div class="grid">
        <div class="quadrant">
            <div class="quadrant-title">CAMERA 11 (TOP LEFT)</div>
            <img src="/video_feed1" class="camera-feed">
        </div>
        
        <div class="quadrant">
            <div class="quadrant-title">CAMERA 12 (BOTTOM LEFT)</div>
            <img src="/video_feed2" class="camera-feed">
        </div>
        
        <div class="quadrant right-half">
            <div class="quadrant-title">ARENA MAP :: CORNERS 11, 12, 13, 14</div>
            <canvas id="field-canvas"></canvas>
        </div>
    </div>

    <div id="status-bar">
        <span>DEVICE: <span class="highlight">CAR 8</span></span>
        <span id="pos-display">POS: --, --</span>
        <span id="heading-display">HEADING: --°</span>
        <span id="target-display">TARGET: --</span>
    </div>

    <script>
        async function setTarget(q) {
            await fetch(`/set_target/${q}`);
        }

        const canvas = document.getElementById('field-canvas');
        const ctx = canvas.getContext('2d');
        let size = 0;
        let margin = 60;

        function resizeCanvas() {
            canvas.width = canvas.clientWidth;
            canvas.height = canvas.clientHeight;
            size = Math.min(canvas.width, canvas.height);
        }
        window.addEventListener('resize', resizeCanvas);
        resizeCanvas();

        function toCanvas(x, y) {
            const innerSize = size - 2 * margin;
            const offsetX = (canvas.width - size) / 2 + margin;
            const offsetY = (canvas.height - size) / 2 + margin;
            return {
                x: offsetX + x * innerSize,
                y: offsetY + (1 - y) * innerSize
            };
        }

        async function updateState() {
            try {
                const response = await fetch('/state');
                const state = await response.json();
                
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                const innerSize = size - 2 * margin;
                const offsetX = (canvas.width - size) / 2 + margin;
                const offsetY = (canvas.height - size) / 2 + margin;
                
                // Draw Grid
                ctx.strokeStyle = '#222';
                ctx.lineWidth = 1;
                ctx.beginPath();
                for(let i=0; i<=4; i++) {
                    const p1 = toCanvas(i/4, 0); const p2 = toCanvas(i/4, 1);
                    ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y);
                    const p3 = toCanvas(0, i/4); const p4 = toCanvas(1, i/4);
                    ctx.moveTo(p3.x, p3.y); ctx.lineTo(p4.x, p4.y);
                }
                ctx.stroke();

                // Draw Field Boundary
                ctx.strokeStyle = '#333';
                ctx.lineWidth = 2;
                ctx.strokeRect(offsetX, offsetY, innerSize, innerSize);

                // Draw Corner Markers
                ctx.fillStyle = '#03dac6';
                ctx.font = 'bold 16px Inter';
                ctx.textAlign = 'center';
                const cornerCoords = [
                    {x:0, y:1, label:'11'}, {x:1, y:1, label:'12'},
                    {x:1, y:0, label:'13'}, {x:0, y:0, label:'14'}
                ];
                cornerCoords.forEach(c => {
                    const p = toCanvas(c.x, c.y);
                    ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI*2); ctx.fill();
                    ctx.fillStyle = '#999';
                    ctx.fillText(c.label, p.x + (c.x ? 20 : -20), p.y + (c.y ? -15 : 25));
                    ctx.fillStyle = '#03dac6';
                });

                // Target Quadrant
                if (state.target_q && state.target_q <= 4 && state.target_q > 0) {
                    ctx.fillStyle = 'rgba(207, 102, 121, 0.15)';
                    let qx = 0, qy = 0;
                    if (state.target_q === 1) { qx = 0.5; qy = 0.5; }
                    if (state.target_q === 2) { qx = 0; qy = 0.5; }
                    if (state.target_q === 3) { qx = 0; qy = 0; }
                    if (state.target_q === 4) { qx = 0.5; qy = 0; }
                    const p = toCanvas(qx, qy + 0.5);
                    ctx.fillRect(p.x, p.y, innerSize/2, innerSize/2);
                    ctx.strokeStyle = '#cf6679';
                    ctx.strokeRect(p.x, p.y, innerSize/2, innerSize/2);
                    document.getElementById('target-display').innerHTML = `TARGET: <span class="highlight">Q${state.target_q}</span>`;
                } else if (state.target_q >= 11) {
                    document.getElementById('target-display').innerHTML = `TARGET: <span class="highlight">CORNER ${state.target_q}</span>`;
                } else {
                    document.getElementById('target-display').innerHTML = `TARGET: <span class="highlight">AUTO</span>`;
                }

                // Car 8
                const car = toCanvas(state.car_pos[0], state.car_pos[1]);
                ctx.save();
                ctx.translate(car.x, car.y);
                ctx.rotate(-state.car_heading); 
                ctx.fillStyle = '#bb86fc';
                ctx.beginPath(); ctx.moveTo(18, 0); ctx.lineTo(-12, -10); ctx.lineTo(-12, 10); ctx.closePath(); ctx.fill();
                ctx.restore();
                
                ctx.fillStyle = '#e0e0e0'; ctx.font = '12px Inter';
                ctx.fillText("CAR 8", car.x, car.y + 25);

                document.getElementById('pos-display').innerText = `POS: ${state.car_pos[0].toFixed(2)}, ${state.car_pos[1].toFixed(2)}`;
                document.getElementById('heading-display').innerText = `HEADING: ${(state.car_heading * 180 / Math.PI).toFixed(1)}°`;
            } catch (e) { console.error(e); }
        }
        setInterval(updateState, 100);
    </script>
</body>
</html>
            """)

        @self.app.route('/video_feed1')
        def video_feed1():
            return Response(self._generate_frames(1),
                            mimetype='multipart/x-mixed-replace; boundary=frame')

        @self.app.route('/video_feed2')
        def video_feed2():
            return Response(self._generate_frames(2),
                            mimetype='multipart/x-mixed-replace; boundary=frame')

        @self.app.route('/state')
        def get_state():
            with self.lock:
                return self.field_state

        @self.app.route('/set_target/<int:q>')
        def set_target(q):
            with self.lock:
                self.field_state["target_q"] = q
            return {"status": "ok", "target_q": q}

    def _generate_frames(self, cam_id):
        while True:
            with self.lock:
                frame = self.frame1 if cam_id == 1 else self.frame2
                if frame is None:
                    time.sleep(0.05)
                    continue
                ret, buffer = cv2.imencode('.jpg', frame)
                frame_bytes = buffer.tobytes()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.05)

    def update(self, frame1=None, frame2=None, car_pos=None, car_heading=None, target_q=None):
        with self.lock:
            if frame1 is not None: self.frame1 = frame1
            if frame2 is not None: self.frame2 = frame2
            if car_pos is not None:
                self.field_state["car_pos"] = [float(car_pos[0]), float(car_pos[1])]
            if car_heading is not None:
                self.field_state["car_heading"] = float(car_heading)
            if target_q is not None:
                self.field_state["target_q"] = target_q

    def _run(self):
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        self.app.run(host=self.host, port=self.port, threaded=True, use_reloader=False)

    def start(self):
        self.thread.start()
        print(f"Visualization server started at http://{self.host}:{self.port}")
