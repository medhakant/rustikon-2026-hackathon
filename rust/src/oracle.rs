use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::Duration;
use serde_json::Value;

pub struct OracleClient {
    host: String,
    port: u16,
    token: String,
}

impl OracleClient {
    pub fn new(host: &str, token: &str, port: u16) -> Self {
        Self {
            host: host.to_string(),
            port,
            token: token.to_string(),
        }
    }

    pub fn get_target_quadrant(&self) -> Option<i32> {
        let addr = format!("{}:{}", self.host, self.port);
        if let Ok(mut stream) = TcpStream::connect(&addr) {
            let _ = stream.set_read_timeout(Some(Duration::from_secs(1)));
            let req = format!("GET /quadrant HTTP/1.1\r\nHost: {}\r\nAuthorization: {}\r\nConnection: close\r\n\r\n", self.host, self.token);
            let _ = stream.write_all(req.as_bytes());

            let mut resp = String::new();
            if stream.read_to_string(&mut resp).is_ok() {
                if let Some(body_idx) = resp.find("\r\n\r\n") {
                    let body = &resp[body_idx + 4..];
                    if let Ok(json) = serde_json::from_str::<Value>(body) {
                        if let Some(quad) = json.get("quadrant") {
                            if let Some(num) = quad.as_i64() {
                                return Some(num as i32);
                            }
                        }
                    }
                }
            }
        }
        None
    }
}
