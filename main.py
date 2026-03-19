import time
import math
import numpy as np

from car import CarClient
from camera import CameraClient
from oracle import OracleClient
from vision import VisionSystem

def angle_diff(target, current):
    # Returns the shortest difference between two angles in [-pi, pi]
    diff = target - current
    return (diff + math.pi) % (2 * math.pi) - math.pi

class MainController:
    def __init__(self, car_id: int):
        self.car_id = car_id
        # In a real scenario, IPs and tokens would be loaded from env vars
        self.car = CarClient(f"hackathon-{car_id}-car.local", "000000")
        self.cam1 = CameraClient("hackathon-11-camera.local", "123456")
        self.cam2 = CameraClient("hackathon-12-camera.local", "123456")
        
        # Placeholder IP for Oracle; will be provided at venue
        self.oracle = OracleClient("192.168.0.100", "123456", port=8080)
        
        # Corner IDs assuming [TL, TR, BR, BL]
        self.vision = VisionSystem([0, 1, 2, 3])
        
        self.H1 = None
        self.H2 = None
        self.heading_offset = 0.0
        
    def setup_vision(self):
        print("Setting up vision and homography...")
        while self.H1 is None and self.H2 is None:
            f1 = self.cam1.get_frame()
            f2 = self.cam2.get_frame()
            
            if f1 is not None:
                res1 = self.vision.detect_markers(f1)
                self.H1 = self.vision.compute_homography(res1)
                if self.H1 is not None:
                    print("Homography H1 computed.")
                    
            if f2 is not None:
                res2 = self.vision.detect_markers(f2)
                self.H2 = self.vision.compute_homography(res2)
                if self.H2 is not None:
                    print("Homography H2 computed.")
                    
            if self.H1 is None and self.H2 is None:
                print("Could not find all 4 corners in either camera. Retrying in 1s.")
                time.sleep(1.0)
                
    def get_pose(self):
        f1 = self.cam1.get_frame()
        f2 = self.cam2.get_frame()
        return self.vision.get_car_pose(f1, f2, self.car_id, self.H1, self.H2)

    def calibrate(self):
        print("Starting calibration pulse...")
        self.car.start_heartbeat()
        
        # Allow time for cameras/car to settle
        time.sleep(1.0)
        pose_start = self.get_pose()
        if not pose_start:
            print("Car not visible for calibration!")
            return False
            
        start_pos, start_heading = pose_start
        
        # Pulse forward to find true forward vector
        self.car.set_command(0.5, False)
        time.sleep(0.5)
        self.car.stop_car()
        time.sleep(0.5)
        
        pose_end = self.get_pose()
        if not pose_end:
            print("Car lost after calibration pulse!")
            return False
            
        end_pos, end_heading = pose_end
        
        d_pos = end_pos - start_pos
        dist = np.linalg.norm(d_pos)
        if dist < 0.02:
            print(f"Car didn't move enough to calibrate (dist: {dist:.3f}). Proceeding with 0 offset.")
            self.heading_offset = 0.0
            return True
            
        physical_heading = np.arctan2(d_pos[1], d_pos[0])
        self.heading_offset = angle_diff(physical_heading, end_heading)
        
        print(f"Calibration successful. Heading offset: {math.degrees(self.heading_offset):.1f} deg")
        return True

    def run_loop(self):
        self.setup_vision()
        if not self.calibrate():
            print("Calibration failed. Exiting.")
            self.car.stop_heartbeat()
            return
            
        lost_time = 0.0
        last_loop_time = time.time()
        
        target_q = None
        
        # Quadrant centers matching Cartesian layout:
        # Q1: Top-Right (x>0.5, y>0.5) -> Center (0.75, 0.75)
        # Q2: Top-Left (x<0.5, y>0.5) -> Center (0.25, 0.75)
        # Q3: Bottom-Left (x<0.5, y<0.5) -> Center (0.25, 0.25)
        # Q4: Bottom-Right (x>0.5, y<0.5) -> Center (0.75, 0.25)
        centers = {
            1: np.array([0.75, 0.75]),
            2: np.array([0.25, 0.75]),
            3: np.array([0.25, 0.25]),
            4: np.array([0.75, 0.25]),
        }
        
        while True:
            t = time.time()
            dt = t - last_loop_time
            last_loop_time = t
            
            # 1. Update target every ~2 seconds
            if int(t) % 2 == 0:
                new_q = self.oracle.get_target_quadrant()
                if new_q is not None and new_q != target_q:
                    print(f"New Target Quadrant received from Oracle: {new_q}")
                    target_q = new_q
                    
            if target_q is None:
                time.sleep(0.1)
                continue
                
            target_pos = centers.get(target_q, np.array([0.5, 0.5]))
            
            # 2. Get pose
            pose = self.get_pose()
            if pose is None:
                lost_time += dt
                if lost_time > 2.0:
                    # Recovery pivot
                    print("Car Lost! Initiating recovery wiggle...")
                    self.car.set_command(0.35, True)
                elif lost_time > 0.5:
                    # Safety stop
                    self.car.stop_car()
                time.sleep(0.1)
                continue
                
            lost_time = 0.0
            pos, marker_heading = pose
            
            # 3. Vision mapping to standard Cartesian
            # Invert Y because image Y increases downwards, but quadrants expect Cartesian (Y up)
            pos_cartesian = np.array([pos[0], 1.0 - pos[1]])
            
            # Apply offset from calibration and negate Y-axis effect on angle
            physical_heading_img = marker_heading + self.heading_offset
            heading = -physical_heading_img
            
            # 4. Control logic (Proportional Controller)
            dist = np.linalg.norm(target_pos - pos_cartesian)
            
            if dist < 0.25: # Margin to settle comfortably within quadrant (bounds are 0.5x0.5)
                self.car.stop_car()
                # Print once every second to avoid spam
                if int(t*10) % 10 == 0:
                    print(f"SETTLED in Quadrant {target_q}. Awaiting new target...")
            else:
                target_vec = target_pos - pos_cartesian
                target_heading = np.arctan2(target_vec[1], target_vec[0])
                
                err_heading = angle_diff(target_heading, heading)
                
                # Turn vs Drive state
                if abs(err_heading) > math.radians(20):
                    # Rotate in place (flip=True). Positive speed = Clockwise.
                    # err_heading > 0 means target is CCW, so we want CCW rotation (speed < 0)
                    turn_speed = -0.45 if err_heading > 0 else 0.45
                    self.car.set_command(turn_speed, True)
                else:
                    # Heading aligned, drive forward
                    drive_speed = min(0.4 + 0.5 * dist, 1.0)
                    self.car.set_command(drive_speed, False)
                        
            time.sleep(0.05) 

if __name__ == "__main__":
    ctrl = MainController(car_id=9)
    try:
        ctrl.run_loop()
    except KeyboardInterrupt:
        print("\nShutting down controller...")
        ctrl.car.stop_heartbeat()
