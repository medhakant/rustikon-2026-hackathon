use crate::car::CarClient;
use crate::oracle::OracleClient;
use crate::camera::CameraClient;
use crate::vision::VisionSystem;

use opencv::core::{Mat, Point2f};
use std::f64::consts::PI;
use std::time::{Duration, Instant};
use std::thread;

pub fn angle_diff(target: f64, current: f64) -> f64 {
    let diff = target - current;
    (diff + PI).rem_euclid(2.0 * PI) - PI
}

pub struct Controller {
    status: String,
    speed: f64,
    flip: i32,
    logs: Vec<String>,
    pub car: CarClient,
    pub oracle: OracleClient,
    pub vision: VisionSystem,
    pub cam1: CameraClient,
    pub cam2: CameraClient,
    pub h1: Option<Mat>,
    pub h2: Option<Mat>,
    pub heading_offset: f64,
    pub car_id: i32,
}

impl Controller {
    pub fn new() -> Self {
        let car = CarClient::new("127.0.0.1", "hackathon_token", 50051);
        let oracle = OracleClient::new("127.0.0.1", "hackathon_token", 50051);
        let cam1 = CameraClient::new("127.0.0.1", "hackathon_token", 50051);
        let cam2 = CameraClient::new("127.0.0.1", "hackathon_token", 50052);
        let vision = VisionSystem::new(vec![0, 1, 2, 3]).unwrap();

        Self {
            status: "IDLE".to_string(),
            speed: 0.0,
            flip: 0,
            logs: vec!["[INFO] System initialized.".to_string(), "[INFO] Waiting for commands...".to_string()],
            car,
            oracle,
            vision,
            cam1,
            cam2,
            h1: None,
            h2: None,
            heading_offset: 0.0,
            car_id: 9,
        }
    }

    pub fn robot_status(&self) -> String {
        format!(r#"{{
    "status": "{}",
    "speed": {:.1},
    "flip": {}
}}"#, self.status, self.speed, self.flip)
    }

    pub fn sensor_data(&self) -> String {
        r#"{
    "position_top": {
        "robot_x": 125.0,
        "robot_y": 125.0,
        "target_x": 125.0,
        "target_y": 50.0,
        "marker_x": [110.0, 140.0, 140.0, 110.0],
        "marker_y": [110.0, 110.0, 140.0, 140.0]
    },
    "position_camera1": {
        "robot_x": 0.0,
        "robot_y": 0.0,
        "target_x": 0.0,
        "target_y": 0.0,
        "marker_x": [0.0, 0.0, 0.0, 0.0],
        "marker_y": [0.0, 0.0, 0.0, 0.0]
    },
    "position_camera2": {
        "robot_x": 0.0,
        "robot_y": 0.0,
        "target_x": 0.0,
        "target_y": 0.0,
        "marker_x": [0.0, 0.0, 0.0, 0.0],
        "marker_y": [0.0, 0.0, 0.0, 0.0]
    }
}"#.to_string()
    }

    pub fn report_status(&self) -> String {
        let rs = self.robot_status();
        let sd = self.sensor_data();
        let logs_json = format!("{:?}", self.logs);
        
        let rs_inner = rs.trim().trim_start_matches('{').trim_end_matches('}');
        let sd_inner = sd.trim().trim_start_matches('{').trim_end_matches('}');

        format!("{{{}, \n    \"log\": {},\n{}}}", rs_inner, logs_json, sd_inner)
    }

    pub fn report_log(&self) -> &[String] {
        &self.logs
    }

    pub fn log_msg(&mut self, msg: &str) {
        println!("{}", msg);
        self.logs.push(msg.to_string());
    }

    pub fn setup_vision(&mut self) {
        self.log_msg("Setting up vision and homography...");
        while self.h1.is_none() || self.h2.is_none() {
            let f1 = self.cam1.get_frame();
            let f2 = self.cam2.get_frame();

            if let Some(ref img1) = f1 {
                if let Ok(res1) = self.vision.detect_markers(img1) {
                    if let Ok(Some(mat)) = self.vision.compute_homography(&res1) {
                        self.h1 = Some(mat);
                        self.log_msg("Homography H1 computed.");
                    }
                }
            }

            if let Some(ref img2) = f2 {
                if let Ok(res2) = self.vision.detect_markers(img2) {
                    if let Ok(Some(mat)) = self.vision.compute_homography(&res2) {
                        self.h2 = Some(mat);
                        self.log_msg("Homography H2 computed.");
                    }
                }
            }

            if self.h1.is_none() && self.h2.is_none() {
                self.log_msg("Could not find all 4 corners in either camera. Retrying in 1s.");
                thread::sleep(Duration::from_secs(1));
            }
        }
    }

    pub fn get_pose(&mut self) -> Option<(Point2f, f64)> {
        let f1 = self.cam1.get_frame();
        let f2 = self.cam2.get_frame();
        
        if let Ok(pose) = self.vision.get_car_pose(
            f1.as_ref(),
            f2.as_ref(),
            self.car_id,
            self.h1.as_ref(),
            self.h2.as_ref(),
        ) {
            pose
        } else {
            None
        }
    }

    pub fn calibrate(&mut self) -> bool {
        self.status = "CALIBRATING".to_string();
        self.log_msg("Starting calibration pulse...");
        self.car.start_heartbeat();

        thread::sleep(Duration::from_secs(1));
        let pose_start = self.get_pose();
        if pose_start.is_none() {
            self.log_msg("Car not visible for calibration!");
            return false;
        }

        let (start_pos, _start_heading) = pose_start.unwrap();

        self.car.set_command(0.5, false, true);
        thread::sleep(Duration::from_millis(500));
        self.car.stop_car();
        thread::sleep(Duration::from_millis(500));

        let pose_end = self.get_pose();
        if pose_end.is_none() {
            self.log_msg("Car lost after calibration pulse!");
            return false;
        }

        let (end_pos, end_heading) = pose_end.unwrap();

        let dx = (end_pos.x - start_pos.x) as f64;
        let dy = (end_pos.y - start_pos.y) as f64;
        let dist = (dx * dx + dy * dy).sqrt();

        if dist < 0.02 {
            self.log_msg(&format!("Car didn't move enough to calibrate (dist: {:.3}). Proceeding with 0 offset.", dist));
            self.heading_offset = 0.0;
            return true;
        }

        let physical_heading = dy.atan2(dx);
        self.heading_offset = angle_diff(physical_heading, end_heading);

        self.log_msg(&format!("Calibration successful. Heading offset: {:.1} deg", self.heading_offset.to_degrees()));
        true
    }

    pub fn start(&mut self) {
        self.status = "RUNNING".to_string();
        self.speed = 1.0;
        self.flip = 1;
        self.log_msg("[CMD] Started robot. Run Loop should take over.");
    }

    pub fn stop(&mut self) {
        self.status = "STOPPED".to_string();
        self.speed = 0.0;
        self.flip = 0;
        self.log_msg("[CMD] Stopped robot.");
        self.car.stop_car();
        self.car.stop_heartbeat();
    }

    pub fn run_loop(&mut self) {
        self.setup_vision();
        if !self.calibrate() {
            self.log_msg("Calibration failed. Exiting.");
            self.car.stop_heartbeat();
            return;
        }

        let mut lost_time = 0.0;
        let mut last_loop_time = Instant::now();
        let mut target_q: Option<i32> = None;

        let centers = [
            (1, Point2f::new(0.75, 0.75)),
            (2, Point2f::new(0.25, 0.75)),
            (3, Point2f::new(0.25, 0.25)),
            (4, Point2f::new(0.75, 0.25)),
        ];

        let start_time = Instant::now();

        loop {
            let t = start_time.elapsed().as_secs_f64();
            let dt = last_loop_time.elapsed().as_secs_f64();
            last_loop_time = Instant::now();

            if (t as u64) % 2 == 0 {
                if let Some(new_q) = self.oracle.get_target_quadrant() {
                    if Some(new_q) != target_q {
                        self.log_msg(&format!("New Target Quadrant received from Oracle: {}", new_q));
                        target_q = Some(new_q);
                    }
                }
            }

            if target_q.is_none() {
                thread::sleep(Duration::from_millis(100));
                continue;
            }

            let q_val = target_q.unwrap();
            let mut target_pos = Point2f::new(0.5, 0.5);
            for &(id, pt) in &centers {
                if id == q_val {
                    target_pos = pt;
                }
            }

            if let Some(pose) = self.get_pose() {
                lost_time = 0.0;
                let (pos, marker_heading) = pose;

                let pos_cartesian_x = pos.x as f64;
                // Invert Y axis
                let pos_cartesian_y = 1.0 - (pos.y as f64);

                let physical_heading_img = marker_heading + self.heading_offset;
                let heading = -physical_heading_img;

                let dx = (target_pos.x as f64) - pos_cartesian_x;
                let dy = (target_pos.y as f64) - pos_cartesian_y;
                let dist = (dx * dx + dy * dy).sqrt();

                if dist < 0.25 {
                    self.car.stop_car();
                    if (t * 10.0) as u64 % 10 == 0 {
                        self.log_msg(&format!("SETTLED in Quadrant {}. Awaiting new target...", q_val));
                    }
                } else {
                    let target_heading = dy.atan2(dx);
                    let err_heading = angle_diff(target_heading, heading);

                    // Turn vs Drive state
                    if err_heading.abs() > 20.0_f64.to_radians() {
                        let turn_speed = if err_heading > 0.0 { -0.45 } else { 0.45 };
                        self.car.set_command(turn_speed, true, true);
                    } else {
                        let drive_speed = (0.4 + 0.5 * dist).min(1.0);
                        self.car.set_command(drive_speed, false, true);
                    }
                }
            } else {
                lost_time += dt;
                if lost_time > 2.0 {
                    self.log_msg("Car Lost! Initiating recovery wiggle...");
                    self.car.set_command(0.35, true, true);
                } else if lost_time > 0.5 {
                    self.car.stop_car();
                }
            }

            thread::sleep(Duration::from_millis(50));
        }
    }
}
