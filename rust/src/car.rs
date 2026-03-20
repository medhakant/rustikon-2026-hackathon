use serde::Serialize;
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;
use std::io::Write;
use std::net::TcpStream;

#[derive(Serialize)]
struct CarPayload {
    speed: f64,
    flip: bool,
}

pub struct CarClient {
    host: String,
    port: u16,
    token: String,
    speed: Arc<Mutex<f64>>,
    flip: Arc<Mutex<bool>>,
    running: Arc<Mutex<bool>>,
    thread_handle: Option<JoinHandle<()>>,
}

impl CarClient {
    pub fn new(host: &str, token: &str, port: u16) -> Self {
        Self {
            host: host.to_string(),
            port,
            token: token.to_string(),
            speed: Arc::new(Mutex::new(0.0)),
            flip: Arc::new(Mutex::new(false)),
            running: Arc::new(Mutex::new(false)),
            thread_handle: None,
        }
    }

    pub fn set_command(&self, mut speed: f64, flip: bool, enforce_deadband: bool) {
        if enforce_deadband && speed != 0.0 {
            if speed > 0.0 && speed < 0.35 {
                speed = 0.35;
            } else if speed < 0.0 && speed > -0.35 {
                speed = -0.35;
            }
        }

        speed = speed.clamp(-1.0, 1.0);

        *self.speed.lock().unwrap() = speed;
        *self.flip.lock().unwrap() = flip;
    }

    pub fn stop_car(&self) {
        self.set_command(0.0, false, false);
    }

    pub fn start_heartbeat(&mut self) {
        let mut running = self.running.lock().unwrap();
        if *running {
            return;
        }
        *running = true;

        let running_clone = Arc::clone(&self.running);
        let speed_clone = Arc::clone(&self.speed);
        let flip_clone = Arc::clone(&self.flip);
        let host = self.host.clone();
        let port = self.port;
        let token = self.token.clone();

        let handle = thread::spawn(move || {
            let addr = format!("{}:{}", host, port);

            while *running_clone.lock().unwrap() {
                let speed = *speed_clone.lock().unwrap();
                let flip = *flip_clone.lock().unwrap();

                let payload = CarPayload { speed, flip };
                let payload_str = serde_json::to_string(&payload).unwrap_or_default();
                
                if let Ok(mut stream) = TcpStream::connect(&addr) {
                    let _ = stream.set_write_timeout(Some(Duration::from_millis(80)));
                    let req = format!(
                        "PUT / HTTP/1.1\r\nHost: {}\r\nAuthorization: {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                        host, token, payload_str.len(), payload_str
                    );
                    let _ = stream.write_all(req.as_bytes());
                }

                thread::sleep(Duration::from_millis(100));
            }
        });

        self.thread_handle = Some(handle);
        println!("[CarClient] Heartbeat started.");
    }

    pub fn stop_heartbeat(&mut self) {
        *self.running.lock().unwrap() = false;
        if let Some(handle) = self.thread_handle.take() {
            let _ = handle.join();
        }
        self.stop_car();
        println!("[CarClient] Heartbeat stopped.");
    }
}
