import cv2
import cv2.aruco as aruco
import numpy as np

class VisionSystem:
    def __init__(self, corner_ids=[0, 1, 2, 3]):
        # Expected order: top-left, top-right, bottom-right, bottom-left
        self.corner_ids = corner_ids
        
        # Use 4x4 dictionary as specified
        self.aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_250)
        self.parameters = aruco.DetectorParameters()
        self.detector = aruco.ArucoDetector(self.aruco_dict, self.parameters)
        
    def detect_markers(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        contrast_imgs = [("Base Grayscale", gray)]
        # Alpha-Beta Sweeps
        for alpha in [1.2, 1.5, 2.0, 3.0]:
            for beta in [0, 10, 30, 50, -20]:
                contrast_imgs.append((f"Abs a:{alpha} b:{beta}", cv2.convertScaleAbs(gray, alpha=alpha, beta=beta)))
                
        # CLAHE Sweeps
        for cl in [2.0, 4.0, 6.0]:
            for ts in [4, 8, 16]:
                contrast_imgs.append((f"CLAHE {cl} {ts}", cv2.createCLAHE(clipLimit=cl, tileGridSize=(ts,ts)).apply(gray)))
                
        # Gamma sweeps
        for gamma in [0.7, 1.5, 2.0]:
            invGamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** invGamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
            contrast_imgs.append((f"Gamma {gamma}", cv2.LUT(gray, table)))

        all_found_ids_list = []
        all_corners = []
        
        # Ensure perimeter threshold is safe to prevent noise
        self.parameters.minMarkerPerimeterRate = 0.03
        
        for c_name, c_img in contrast_imgs:
            corners, ids, rejected = self.detector.detectMarkers(c_img)
            if ids is not None and len(ids) > 0:
                for corn, id_val in zip(corners, ids.flatten()):
                    if id_val not in all_found_ids_list:
                        all_found_ids_list.append(id_val)
                        all_corners.append(corn)
                        
        results = {}
        for i, marker_id in enumerate(all_found_ids_list):
            # corners[i] has shape (1, 4, 2)
            c_pts = all_corners[i][0]
            center = np.mean(c_pts, axis=0)
            
            # Bounding box area approximation
            area = cv2.contourArea(c_pts)
            
            # Midpoint of the "top" edge defines the forward vector
            mid_top = (c_pts[0] + c_pts[1]) / 2.0
            forward_vec = mid_top - center
            
            # Heading in radians
            heading = np.arctan2(forward_vec[1], forward_vec[0])
            
            results[marker_id] = {
                "corners": c_pts,
                "center": center,  # (x, y)
                "area": area,
                "heading": heading
            }
        return results

    def compute_homography(self, detected_markers):
        """
        Given markers detected in a camera frame, computes the perspective transform
        mapping the 4 corners to a normalized [0,1]x[0,1] square.
        """
        src_points = []
        dst_points = np.array([
            [0.0, 0.0],  # top-left
            [1.0, 0.0],  # top-right
            [1.0, 1.0],  # bottom-right
            [0.0, 1.0]   # bottom-left
        ], dtype=np.float32)
        
        for c_id in self.corner_ids:
            if c_id not in detected_markers:
                return None  # We need all 4 corners to compute homography
            src_points.append(detected_markers[c_id]["center"])
            
        src_points = np.array(src_points, dtype=np.float32)
        H, _ = cv2.getPerspectiveTransform(src_points, dst_points)
        return H

    def get_car_pose(self, image1, image2, car_id, H1, H2):
        """
        Given the frames from both cameras and their respective Homography matrices,
        detects the car and returns its normalized position and heading.
        """
        res1 = self.detect_markers(image1) if image1 is not None else {}
        res2 = self.detect_markers(image2) if image2 is not None else {}
        
        poses = []
        areas = []
        
        def process_pose(res, H):
            if car_id in res and H is not None:
                m = res[car_id]
                center = m["center"].reshape(1, 1, 2)  # shape needed for perspectiveTransform
                center_t = cv2.perspectiveTransform(center, H)[0][0]
                
                # To transform angle correctly, project a forward point
                forward_pt = m["center"] + np.array([np.cos(m["heading"]), np.sin(m["heading"])])
                forward_pt_t = cv2.perspectiveTransform(forward_pt.reshape(1, 1, 2), H)[0][0]
                
                heading_t = np.arctan2(forward_pt_t[1] - center_t[1], forward_pt_t[0] - center_t[0])
                
                return center_t, heading_t, m["area"]
            return None

        # Camera 1
        pose1 = process_pose(res1, H1)
        if pose1:
            poses.append((pose1[0], pose1[1]))
            areas.append(pose1[2])
            
        # Camera 2
        pose2 = process_pose(res2, H2)
        if pose2:
            poses.append((pose2[0], pose2[1]))
            areas.append(pose2[2])
            
        if not poses:
            return None
            
        # If only seen by one camera
        if len(poses) == 1:
            x, y = poses[0][0]
            heading = poses[0][1]
            return np.array([x, y]), heading
            
        # If seen by both, compute weighted average based on area (closer = more reliable)
        total_area = sum(areas)
        w1 = areas[0] / total_area
        w2 = areas[1] / total_area
        
        avg_x = poses[0][0][0] * w1 + poses[1][0][0] * w2
        avg_y = poses[0][0][1] * w1 + poses[1][0][1] * w2
        
        # Average heading via circular mean
        x_dir = np.cos(poses[0][1]) * w1 + np.cos(poses[1][1]) * w2
        y_dir = np.sin(poses[0][1]) * w1 + np.sin(poses[1][1]) * w2
        avg_heading = np.arctan2(y_dir, x_dir)
        
        return np.array([avg_x, avg_y]), avg_heading
