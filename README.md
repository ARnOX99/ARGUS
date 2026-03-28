# ARGUS v2.0 — Adaptive Real-time Guardian for Unified Surveillance

> AI-powered **offline** classroom exam malpractice detection.  
> Single webcam · 40 students · Pen-paper exams · Fully offline · No student laptops needed.

**Vishwakarma Institute of Technology, Pune**  
CSE (Artificial Intelligence & Machine Learning) | 1st Year, Semester 2 | AY 2025-26  
Division E · Group 1 · 5 Members · 8-Week Timeline · Budget under ₹2,500

---

## What ARGUS Does

A single webcam mounted at the top corner of an exam hall monitors all students simultaneously.  
Instead of firing alerts on every suspicious frame (which causes alert fatigue), ARGUS builds a  
**Cumulative Suspicion Score** per bench over the full exam. Only sustained or repeated patterns  
cross the alert threshold — triggering both the Flask web dashboard **and** a physical Arduino  
console on the teacher's desk (LCD + RGB LED + buzzer). The teacher never needs to stare at  
a laptop screen.

### Three Detection Layers

| Layer | Tools | What It Does |
|-------|-------|--------------|
| Perception | MediaPipe Pose + OpenCV | 33 body landmarks per person · motion intensity per bench zone |
| Intelligence | Random Forest + Score Manager | 7 features → suspicion probability → cumulative score with decay |
| Action | Flask Dashboard + Arduino Console | Live score updates every second · physical alert on teacher's desk |

---

## Hardware Required

| Component | Qty | Cost (₹) |
|-----------|-----|----------|
| Arduino Uno R3 | 1 | 350–500 |
| I2C LCD 16×2 (PCF8574) | 1 | 180–250 |
| RGB LED (common cathode, 5mm) | 2 | 20–30 |
| Passive Buzzer (5V) | 1 | 20–40 |
| 220Ω Resistors | 5 | 10–15 |
| Half Breadboard (400 tie-points) | 1 | 80–120 |
| Jumper Wires (M-to-M, 20cm) | 1 set | 50–80 |
| USB Type-B Cable | 1 | 0–50 |
| Webcam (720p USB, wide-angle 90° FOV) | 1 | 700–1000 |
| Project Box (plastic enclosure) | 1 | 60–100 |
| ArUco Marker Cards (printed A4, laminated) | 40 | 50–100 |
| **TOTAL** | | **₹1,520–₹2,285** |

> ArUco marker cards are plain A4 paper printouts — zero cost if institution printer is available.

---

## Software Requirements

**Python 3.9+** is required. Install all dependencies:

```bash
pip install -r requirements.txt
```

> ⚠️ **Important:** Install `opencv-contrib-python`, NOT `opencv-python`.  
> The ArUco module (`cv2.aruco`) is only in the contrib package.  
> ```bash
> pip uninstall opencv-python
> pip install opencv-contrib-python
> ```

**Arduino IDE** (v2.x) — [arduino.cc](https://www.arduino.cc)  
Install `LiquidCrystal_I2C` via Arduino Library Manager.

---

## How to Run

### 1. Clone the repo
```bash
git clone https://github.com/<your-username>/ARGUS.git
cd ARGUS
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Flash Arduino
- Open `arduino/console.ino` in Arduino IDE
- Select board: **Arduino Uno** · Select correct COM port
- Click Upload

### 4. Start ARGUS
```bash
python run.py
```

Open browser at: **http://localhost:5000**

### 5. Pre-exam setup
1. Log in with teacher credentials
2. Upload CSV seating plan on the Setup page
3. Place ArUco marker cards at bench corners → click **Auto-Scan Benches**
4. Select exam mode: **Lenient / Standard / Strict**
5. Click **Start Exam**

---

## Project Structure
