import time
import math
import cv2
import numpy as np

from car import CarClient
from camera import CameraClient
from oracle import OracleClient
from vision import VisionSystem
from visualization import VisualizationServer

def angle_diff(target, current):
    # Returns the shortest difference between two angles in [-pi, pi].
    diff = target - current
    return (diff + math.pi) % (2 * math.pi) - math.pi

class MainController:
    def __init__(self, car_id: int):
        self.car_id = car_id
        # In a real scenario, IPs and tokens would be loaded from env vars
        self.car = CarClient(f"hackathon-{car_id}-car.local", "746007")
        self.cam1 = CameraClient("hackathon-11-camera.local", "983149")
        self.cam2 = CameraClient("hackathon-12-camera.local", "378031")
        
        # Placeholder IP for Oracle; will be provided at venue
        self.oracle = OracleClient("192.168.0.85", port=8000)
        
        # Corner IDs assuming [TL, TR, BR, BL] as requested: 11, 12, 13, 14
        self.vision = VisionSystem([11, 12, 13, 14])
        
        self.H1 = None
        self.H2 = None
        self.heading_offset = 0.0
        
        # Visualization
        self.viz = VisualizationServer()
        self.viz.start()
        
        self.last_f1 = None
        self.last_f2 = None
        
    def setup_vision(self):
        print("Setting up vision and homography...")
        while self.H1 is None and self.H2 is None:
            f1 = self.cam1.get_frame()
            f2 = self.cam2.get_frame()
            
            # Fallback for debugging if needed
            if f1 is None: f1 = cv2.imread("data/20260319_131143.jpg")
            if f2 is None: f2 = cv2.imread("data/20260319_131145.jpg")
            
            if f1 is not None:
                res1 = self.vision.detect_markers(f1)
                self.H1 = self.vision.compute_homography(1, res1)
                if self.H1 is not None:
                    print("Homography H1 solved using accumulated corners.")
                    
            if f2 is not None:
                res2 = self.vision.detect_markers(f2)
                self.H2 = self.vision.compute_homography(2, res2)
                if self.H2 is not None:
                    print("Homography H2 solved using accumulated corners.")
                    
            # Update visualization during setup
            if f1 is not None: self.last_f1 = f1
            if f2 is not None: self.last_f2 = f2
            
            # Combine and draw even if H is not yet computed
            v1 = self.last_f1.copy() if self.last_f1 is not None else None
            if v1 is not None:
                r1 = self.vision.detect_markers(v1)
                v1 = self.vision.draw_visuals(v1, r1, self.H1)
            v2 = self.last_f2.copy() if self.last_f2 is not None else None
            if v2 is not None:
                r2 = self.vision.detect_markers(v2)
                v2 = self.vision.draw_visuals(v2, r2, self.H2)
            
            self.viz.update(frame1=v1, frame2=v2)
                    
            # Debug: Print unique set of detected corners from the persistent caches
            c1_ids = list(self.vision.corner_caches.get(1, {}).keys())
            c2_ids = list(self.vision.corner_caches.get(2, {}).keys())
            print(f"Cam 1 corners seen: {c1_ids}, Cam 2 corners seen: {c2_ids}")
                    
            if self.H1 is None and self.H2 is None:
                print("Could not find all 4 corners in either camera. Retrying in 1s.")
                time.sleep(1.0)
                
    def get_pose(self):
        f1 = self.cam1.get_frame()
        f2 = self.cam2.get_frame()
        
        # Fallback to static images for debugging if cameras are offline
        if f1 is None:
            f1 = cv2.imread("data/20260319_131143.jpg")
        if f2 is None:
            f2 = cv2.imread("data/20260319_131145.jpg")
            
        # Cache frames for visualization if they are not None
        if f1 is not None: self.last_f1 = f1
        if f2 is not None: self.last_f2 = f2
        
        pose = self.vision.get_car_pose(f1, f2, self.car_id, self.H1, self.H2)
        
        # Update visualization using cached frames
        vis_f1 = self.last_f1.copy() if self.last_f1 is not None else None
        if vis_f1 is not None:
            res1 = self.vision.detect_markers(vis_f1)
            vis_f1 = self.vision.draw_visuals(vis_f1, res1, self.H1)
            # Update cache quietly
            self.vision.update_corner_cache(1, res1)
            
        vis_f2 = self.last_f2.copy() if self.last_f2 is not None else None
        if vis_f2 is not None:
            res2 = self.vision.detect_markers(vis_f2)
            vis_f2 = self.vision.draw_visuals(vis_f2, res2, self.H2)
            # Update cache quietly
            self.vision.update_corner_cache(2, res2)
            
        self.viz.update(frame1=vis_f1, frame2=vis_f2)
            
        return pose

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
        time.sleep(0.2)
        
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
        last_time = 0.0
        last_loop_time = time.time()
        target_q = None
        
        # Quadrant centers matching Cartesian layout:
        # Q1: Top-Right (x>0.5, y>0.5) -> Center (0.75, 0.75)
        # Q2: Top-Left (x<0.5, y>0.5) -> Center (0.25, 0.75)
        # Q3: Bottom-Left (x<0.5, y<0.5) -> Center (0.25, 0.25)
        # Q4: Bottom-Right (x>0.5, y<0.5) -> Center (0.75, 0.25)
        # Mappings: Quadrants 1-4 and Corners 11-14
        centers = {
            1: np.array([0.75, 0.75]),
            2: np.array([0.25, 0.75]),
            3: np.array([0.25, 0.25]),
            4: np.array([0.75, 0.25]),
            # Corners (with a small margin so the car doesn't hit the wall)
            11: np.array([0.25, 0.25]), # TL
            12: np.array([0.75, 0.25]), # TR
            13: np.array([0.75, 0.75]), # BR
            14: np.array([0.25, 0.75]), # BL
        }
        dont_poll_oracle = False
        print("Starting loop")
        while True:
            t = time.time()
            dt = t - last_loop_time
            if dt < 0.5:
                continue
            last_loop_time = t
            new_q = None if dont_poll_oracle else self.oracle.get_target_quadrant()
            dont_poll_oracle = False
            if new_q is not None and new_q != target_q:
                print(f"New Target Quadrant received from Oracle: {new_q}")
                target_q = new_q
            if target_q is None:
                time.sleep(0.1)
                continue
                
            target_number = {'TL': 11, 'TR': 12, 'BR': 13, 'BL': 14}.get(target_q, '')
            target_pos = centers.get(target_number, np.array([0.5, 0.5]))
            
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

            pos, marker_heading = pose
            pos_cartesian = np.array([pos[0], 1.0 - pos[1]])
            lost_time = 0.0
            
            # Apply offset from calibration and negate Y-axis effect on angle
            physical_heading_img = marker_heading + self.heading_offset
            heading = -physical_heading_img
            
            # Update Viz state
            self.viz.update(frame1=None, frame2=None, car_pos=pos_cartesian, car_heading=heading, target_q=target_q)
            
            # 4. Control logic (Proportional Controller)
            dist = np.linalg.norm(target_pos - pos_cartesian)
            print(f"Distance to goal: {dist:.3f} from {target_pos} to {pos_cartesian}")

            if dist < 0.05:
                print(f"Goal reached: {target_q} ")
                self.car.stop_car()
                continue

            target_vec = target_pos - pos_cartesian
            target_heading = np.arctan2(target_vec[1], target_vec[0])
            
            err_heading = angle_diff(target_heading, heading)
            if abs(err_heading) > math.radians(20):
                print(f"Correcting Heading: {math.degrees(err_heading):.1f} deg")
                move_speed = (abs(err_heading) * 0.47/math.pi)*(-1 if err_heading > 0 else 1)
                self.car.set_command(move_speed, flip=True)
                time.sleep(0.2)
                self.car.stop_car()
                last_loop_time = 0
                dont_poll_oracle= True

            print("Heading correct. Moving to Goal.")
            self.car.set_command(0.7 * (dist/0.5), False)
            time.sleep(0.3)
            self.car.stop_car()
            
                    


    # def run_loop(self):
    #     self.setup_vision()
    #     if not self.calibrate():
    #         print("Calibration failed. Exiting.")
    #         self.car.stop_heartbeat()
    #         return
            
    #     lost_time = 0.0
    #     last_loop_time = time.time()
        
    #     target_q = None
        
    #     # Quadrant centers matching Cartesian layout:
    #     # Q1: Top-Right (x>0.5, y>0.5) -> Center (0.75, 0.75)
    #     # Q2: Top-Left (x<0.5, y>0.5) -> Center (0.25, 0.75)
    #     # Q3: Bottom-Left (x<0.5, y<0.5) -> Center (0.25, 0.25)
    #     # Q4: Bottom-Right (x>0.5, y<0.5) -> Center (0.75, 0.25)
    #     # Mappings: Quadrants 1-4 and Corners 11-14
    #     centers = {
    #         1: np.array([0.75, 0.75]),
    #         2: np.array([0.25, 0.75]),
    #         3: np.array([0.25, 0.25]),
    #         4: np.array([0.75, 0.25]),
    #         # Corners (with a small margin so the car doesn't hit the wall)
    #         11: np.array([0.05, 0.95]), # TL
    #         12: np.array([0.95, 0.95]), # TR
    #         13: np.array([0.95, 0.05]), # BR
    #         14: np.array([0.05, 0.05]), # BL
    #     }
        
    #     while True:
    #         t = time.time()
    #         dt = t - last_loop_time
    #         last_loop_time = t
            
    #         # 1. Update target
    #         # Check for manual override from the web dashboard first
    #         # manual_q = self.viz.field_state.get("target_q")
    #         manual_q = None
    #         if manual_q is not None and manual_q != 0:
    #             if manual_q != target_q:
    #                 print(f"Manual Target Override received: {manual_q}")
    #                 target_q = manual_q
    #         elif int(t) % 2 == 0:
    #             # If no manual target, poll Oracle
    #             new_q = self.oracle.get_target_quadrant()
    #             if new_q is not None and new_q != target_q:
    #                 print(f"New Target Quadrant received from Oracle: {new_q}")
    #                 target_q = new_q
                    
    #         if target_q is None:
    #             time.sleep(0.1)
    #             continue
                
    #         target_pos = centers.get(target_q, np.array([0.5, 0.5]))
            
    #         # 2. Get pose
    #         pose = self.get_pose()
    #         if pose is None:
    #             lost_time += dt
    #             if lost_time > 2.0:
    #                 # Recovery pivot
    #                 print("Car Lost! Initiating recovery wiggle...")
    #                 self.car.set_command(0.35, True)
    #             elif lost_time > 0.5:
    #                 # Safety stop
    #                 self.car.stop_car()
    #             time.sleep(0.1)
    #             continue
                
    #         lost_time = 0.0
    #         pos, marker_heading = pose
            
    #         # 3. Vision mapping to standard Cartesian
    #         # Invert Y because image Y increases downwards, but quadrants expect Cartesian (Y up)
    #         pos_cartesian = np.array([pos[0], 1.0 - pos[1]])
            
    #         # Apply offset from calibration and negate Y-axis effect on angle
    #         physical_heading_img = marker_heading + self.heading_offset
    #         heading = -physical_heading_img
            
    #         # Update Viz state
    #         self.viz.update(frame1=None, frame2=None, car_pos=pos_cartesian, car_heading=heading, target_q=target_q)
            
    #         # 4. Control logic (Proportional Controller)
    #         dist = np.linalg.norm(target_pos - pos_cartesian)
            
    #         if dist < 0.05: # Margin to settle comfortably within quadrant (bounds are 0.5x0.5)
    #             self.car.stop_car()
    #             # Print once every second to avoid spam
    #             if int(t*10) % 10 == 0:
    #                 print(f"SETTLED in Quadrant {target_q}. Awaiting new target...")
    #         else:
    #             target_vec = target_pos - pos_cartesian
    #             target_heading = np.arctan2(target_vec[1], target_vec[0])
                
    #             err_heading = angle_diff(target_heading, heading)
                
    #             # 4a. Rotation Pulse (Turn in place)
    #             if abs(err_heading) > math.radians(25):
    #                 # Settle time between turn pulses to avoid random spirals
    #                 if t - self.last_turn_time > 0.2:
    #                     # Rotating in place (flip=True). 
    #                     # err_heading > 0 means target is CCW, so we want CCW rotation (speed < 0)
    #                     turn_speed = -0.4 if err_heading > 0 else 0.4
    #                     print(f"[Control] Pulsing Rotation: err={math.degrees(err_heading):.1f}°")
    #                 self.car.set_command(turn_speed, True)
    #                     time.sleep(0.12) # Short pulse
    #                     self.car.stop_car()
    #                     self.last_turn_time = time.time()
    #                 else:
    #                     # Wait for car to settle and vision to stabilize
    #                     self.car.stop_car()
    #             else:
    #                 # 4b. Driving Pulse (Forward)
    #                 if t - self.last_drive_time > 0.2:
    #                     # Heading aligned, drive forward in short pulses for precision
    #                     drive_speed = min(0.4 + 0.4 * dist, 0.5)
    #                     pulse_dur = 0.1 if dist > 0.4 else 0.05
    #                     print(f"[Control] Pulsing Forward: dist={dist:.2f}m")
    #                 self.car.set_command(drive_speed, False)
    #                     time.sleep(pulse_dur)
    #                     self.car.stop_car()
    #                     self.last_drive_time = time.time()
    #                 else:
    #                     self.car.stop_car()
                        
    #         time.sleep(0.05) 

if __name__ == "__main__":
    ctrl = MainController(car_id=8)
    try:
        ctrl.run_loop()
    except KeyboardInterrupt:
        print("\nShutting down controller...")
        ctrl.car.stop_heartbeat()
