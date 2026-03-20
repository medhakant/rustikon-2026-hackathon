use opencv::{
    core::Vector,
    core::Mat,
    imgcodecs,
};
use std::time::Duration;
use std::io::Read;
use std::io::Write;
use std::net::TcpStream;

pub struct CameraClient {
    host: String,
    port: u16,
    token: String,
}

impl CameraClient {
    pub fn new(host: &str, token: &str, port: u16) -> Self {
        Self {
            host: host.to_string(),
            port,
            token: token.to_string(),
        }
    }

    pub fn get_frame(&self) -> Option<Mat> {
        let addr = format!("{}:{}", self.host, self.port);
        if let Ok(mut stream) = TcpStream::connect(&addr) {
            let _ = stream.set_read_timeout(Some(Duration::from_secs(1)));
            let req = format!("GET /frame HTTP/1.1\r\nHost: {}\r\nAuthorization: {}\r\nConnection: close\r\n\r\n", self.host, self.token);
            let _ = stream.write_all(req.as_bytes());

            let mut buf = Vec::new();
            if stream.read_to_end(&mut buf).is_ok() {
                let mut header_end = 0;
                for i in 0..buf.len().saturating_sub(3) {
                    if buf[i] == b'\r' && buf[i+1] == b'\n' && buf[i+2] == b'\r' && buf[i+3] == b'\n' {
                        header_end = i + 4;
                        break;
                    }
                }

                if header_end > 0 && header_end < buf.len() {
                    let image_data = &buf[header_end..];
                    let mut vec = Vector::<u8>::new();
                    for &b in image_data {
                        vec.push(b);
                    }
                    if let Ok(frame) = imgcodecs::imdecode(&vec, imgcodecs::IMREAD_COLOR) {
                        return Some(frame);
                    }
                }
            }
        }
        None
    }
}
