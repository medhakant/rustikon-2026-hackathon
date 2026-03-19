# Rustikon 2026 Hackathon: Car Remote Controller

This project implements a closed-loop control system for a remote-controlled car using external cameras and ArUco markers for localization.

## Prerequisites
- Python 3.9+
- Access to the `hs-hack` Wi-Fi network.

## Setup
1. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Configuration
Before running, update `main.py` with your specific credentials provided at the venue:
- `car_id`: The ID number on the back of your car's ArUco marker.
- `car_token`: Your 6-digit unique authorization token for the car.
- `camera_token`: The token to access the camera feeds.
- `oracle_ip`: The IP address of the central Oracle server.

## Running the Program
```bash
python main.py
```

## How it Works
1. **Calibration**: The script starts by computing a homography matrix from the arena's corner markers to create a normalized 2D coordinate system (`[0, 1]x[0, 1]`). It then performs a 0.5s forward pulse to find the orientation offset of the car's marker.
2. **Control Loop**: The script polls the cameras for the car's position, polls the Oracle for the target quadrant, and uses a proportional controller to drive the car to the target.
3. **Safety**: Includes a 10Hz heartbeat to keep the motor commands active and a "recovery wiggle" if the marker is lost from camera view.

## Tuning Parameters
If the car is behaving erratically, adjust these constants in `main.py`:
- `turn_speed` (currently `0.45`): Increase if the car turns too slowly; decrease if it overshoots.
- `err_heading` threshold (currently `20` deg): The angle at which the car switches from rotating to driving forward.
- `dist < 0.25`: The distance threshold used to consider a quadrant "reached" (settle margin).
- `drive_speed`: The base speed for forward movement; currently scales with distance.

---
*Good luck with the Helsing Oracle!*