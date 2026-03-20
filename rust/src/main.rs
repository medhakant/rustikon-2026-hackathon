mod controller;
mod vision;
mod car;
mod camera;
mod oracle;

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use controller::Controller;

fn handle_data_route(stream: &mut TcpStream, controller: &Controller) {
    let json_data = controller.report_status();
    let response = format!(
        "HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\nAccess-Control-Allow-Origin: *\r\n\r\n{}",
        json_data.len(),
        json_data
    );
    if let Err(e) = stream.write_all(response.as_bytes()) {
        eprintln!("Failed to write to connection: {}", e);
    }
}

fn handle_html_route(stream: &mut TcpStream) {
    let html_content = r#"<!DOCTYPE html>
<html>
<head>
    <title>Rustikon 2026</title>
    <style>
        body { font-family: sans-serif; background: #121212; color: #fff; margin: 0; padding: 20px; display: flex; flex-direction: column; align-items: center; }
        .controls { display: flex; gap: 10px; margin-top: 10px; }
        button { padding: 10px 20px; font-size: 16px; cursor: pointer; background: #333; color: white; border: 1px solid #555; border-radius: 4px; font-weight: bold; }
        button:hover { background: #555; }
        .container { display: flex; gap: 20px; align-items: flex-start; justify-content: center; margin-top: 20px; }
        .visual-container, .status-container, .log-container { display: flex; flex-direction: column; align-items: center; }
        .visual { border: 1px solid #555; width: 250px; height: 250px; background: #222; }
        .status { font-family: monospace; border: 1px solid #555; padding: 10px; width: 250px; height: 250px; background: #222; box-sizing: border-box; white-space: pre-wrap; word-wrap: break-word;}
        .log-container { margin-top: 20px; width: 520px; align-items: stretch; }
        .log { width: 100%; height: 150px; font-family: monospace; resize: none; background: #222; color: #0f0; border: 1px solid #555; padding: 10px; box-sizing: border-box;}
    </style>
</head>
<body>
    <h1>Welcome to Rust hackaton</h1>
    <div class="controls">
        <button onclick="sendCommand('/calibrate')">Calibrate</button>
        <button onclick="sendCommand('/start')">Start</button>
        <button onclick="sendCommand('/stop')">Stop</button>
    </div>
    <div class="container">
        <div class="visual-container">
            <h2>Visual</h2>
            <canvas id="visualCanvas" class="visual" width="250" height="250"></canvas>
        </div>
        <div class="status-container">
            <h2>Status</h2>
            <div id="statusField" class="status">Status: IDLE
Position: (0, 0)</div>
        </div>
    </div>
    <div class="log-container">
        <h2>Log</h2>
        <textarea id="logField" class="log" readonly>[INFO] System initialized.
[INFO] Waiting for AJAX data...</textarea>
    </div>

    <script>
        function sendCommand(endpoint) {
            fetch(endpoint)
                .then(res => console.log(`Sent command to ${endpoint}`))
                .catch(err => console.error(`Error sending to ${endpoint}:`, err));
        }

        const canvas = document.getElementById('visualCanvas');
        const ctx = canvas.getContext('2d');
        
        function drawRobot(x, y, width, height, angle) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.save();
            ctx.translate(x, y);
            ctx.rotate(angle); 
            
            ctx.beginPath();
            ctx.moveTo(-width/2, height/2); // Bottom Left
            ctx.lineTo(width/2, height/2);  // Bottom Right
            ctx.lineTo(width/2, -height/2); // Top Right
            ctx.lineTo(0, -height/2 - 20);  // 5th Vertex (Front point)
            ctx.lineTo(-width/2, -height/2); // Top Left
            ctx.closePath();
            
            ctx.fillStyle = '#4CAF50';
            ctx.fill();
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 2;
            ctx.stroke();
            
            ctx.restore();
        }

        // Draw initial robot in the center
        drawRobot(125, 125, 60, 100, 0);

        // Fetch /data every second and update UI
        setInterval(() => {
            fetch('/data')
                .then(res => res.json())
                .then(data => {
                    // Update Status Field
                    const statusField = document.getElementById('statusField');
                    let pos = data.position_top;
                    statusField.innerText = `Status: ${data.status}\nSpeed: ${data.speed}\nFlip: ${data.flip}\n\nPosition:\n  Robot: (${pos.robot_x.toFixed(1)}, ${pos.robot_y.toFixed(1)})\n  Target: (${pos.target_x.toFixed(1)}, ${pos.target_y.toFixed(1)})`;
                    
                    // Update Log Field
                    const logField = document.getElementById('logField');
                    if (data.log && data.log.length > 0) {
                        logField.value = data.log.join('\n');
                        logField.scrollTop = logField.scrollHeight;
                    }

                    // Update Visual Orientation (pointing towards target)
                    let dx = pos.target_x - pos.robot_x;
                    let dy = pos.target_y - pos.robot_y;
                    let angle = Math.atan2(dy, dx) + Math.PI/2;
                    drawRobot(125, 125, 60, 100, angle);
                })
                .catch(err => console.error("Error fetching data:", err));
        }, 1000);
    </script>
</body>
</html>"#;

    let response = format!(
        "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        html_content.len(),
        html_content
    );

    if let Err(e) = stream.write_all(response.as_bytes()) {
        eprintln!("Failed to write to connection: {}", e);
    }
}

fn handle_ok_response(stream: &mut TcpStream) {
    let response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nAccess-Control-Allow-Origin: *\r\n\r\n{\"status\":\"ok\"}";
    if let Err(e) = stream.write_all(response.as_bytes()) {
        eprintln!("Failed to write to connection: {}", e);
    }
}

fn main() {
    let listener = TcpListener::bind("127.0.0.1:8080").unwrap();
    let mut controller = Controller::new();
    println!("Server running on http://127.0.0.1:8080");

    for stream in listener.incoming() {
        match stream {
            Ok(mut stream) => {
                let mut buffer = [0; 1024];
                let size = match stream.read(&mut buffer) {
                    Ok(size) => size,
                    Err(e) => {
                        eprintln!("Failed to read from connection: {}", e);
                        continue;
                    }
                };

                let request = String::from_utf8_lossy(&buffer[..size]);
                let first_line = request.lines().next().unwrap_or("");
                
                if first_line.starts_with("GET /data ") {
                    handle_data_route(&mut stream, &controller);
                } else if first_line.starts_with("GET /calibrate ") {
                    controller.calibrate();
                    handle_ok_response(&mut stream);
                } else if first_line.starts_with("GET /start ") {
                    controller.start();
                    handle_ok_response(&mut stream);
                } else if first_line.starts_with("GET /stop ") {
                    controller.stop();
                    handle_ok_response(&mut stream);
                } else {
                    handle_html_route(&mut stream);
                }
                
                if let Err(e) = stream.flush() {
                    eprintln!("Failed to flush connection: {}", e);
                }
            }
            Err(e) => {
                eprintln!("Failed to establish a connection: {}", e);
            }
        }
    }
}
