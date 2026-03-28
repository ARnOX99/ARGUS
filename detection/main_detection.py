# main_detection.py
# Purpose: Master detection loop — connects all modules every frame.
#
# v2 Updates included:
#   - 5: Background thread for 60-sec pending-vacant confirmation
#   - 4: contradiction_flag passed through reset_bench()
#   - Zone overlay colors: GREEN / YELLOW / RED / GREY / ORANGE(pending)
#
# Depends on (uncomment imports as each member completes their file):
#   detection/pose_detector.py     
#   detection/feature_extractor.py  
#   detection/motion_zones.py      
#   detection/zone_manager.py       
#   detection/classifier.py         
#   webapp/serial_handler.py       
#   webapp/audit_logger.py          

import cv2
import time
import threading

from detection.score_manager import ScoreManager

# ── Uncomment each line when that member's file is ready ─────────────────────
# from detection.pose_detector     import PoseDetector
# from detection.feature_extractor import FeatureExtractor
# from detection.motion_zones      import MotionZones
# from detection.zone_manager      import ZoneManager
# from detection.classifier        import Classifier
# from webapp.serial_handler       import SerialHandler
# from webapp.audit_logger         import AuditLogger
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

CAMERA_INDEX    = 0
CAMERA_WIDTH    = 1280
CAMERA_HEIGHT   = 720
TARGET_FPS      = 15
DECAY_INTERVAL  = 1.0      # seconds between decay calls
SERIAL_PORT     = "COM3"   # Windows: COM3 / Linux: /dev/ttyUSB0
SERIAL_BAUD     = 9600


# ─────────────────────────────────────────────
# DetectionPipeline
# ─────────────────────────────────────────────

class DetectionPipeline:

    def __init__(self):
        # Member 1 — DONE
        self.score_manager = ScoreManager(config_path="data/config.json")

        # Other members — replace None with real instance when file is ready
        self.pose_detector     = None   # PoseDetector()
        self.feature_extractor = None   # FeatureExtractor()
        self.motion_zones      = None   # MotionZones()
        self.zone_manager      = None   # ZoneManager("data/zones.json")
        self.classifier        = None   # Classifier("ml/classifier.pkl")
        self.serial_handler    = None   # SerialHandler(SERIAL_PORT, SERIAL_BAUD)
        self.audit_logger      = None   # AuditLogger("data/audit_log.json")

        self.cap              = None
        self.prev_frame       = None
        self.running          = False
        self.exam_active      = False
        self.frame_number     = 0
        self.last_decay_time  = time.time()
        self.latest_frame     = None
        self.frame_lock       = threading.Lock()

        print("[DetectionPipeline] Initialized. Waiting for Start Exam signal.")

    # ──────────────────────────────────────────
    # Camera Setup
    # ──────────────────────────────────────────

    def _init_camera(self):
        self.cap = cv2.VideoCapture(CAMERA_INDEX)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS,          TARGET_FPS)
        if not self.cap.isOpened():
            raise RuntimeError("[DetectionPipeline] ERROR: Cannot open webcam.")
        print(f"[DetectionPipeline] Camera opened — {CAMERA_WIDTH}x{CAMERA_HEIGHT} @ {TARGET_FPS}fps")

    # ──────────────────────────────────────────
    # Register all benches from zones.json
    # ──────────────────────────────────────────

    def _register_all_benches(self):
        import json, os
        if not os.path.exists("data/zones.json"):
            print("[DetectionPipeline] WARNING: zones.json not found.")
            return
        with open("data/zones.json", "r") as f:
            zones = json.load(f)
        for zone in zones:
            self.score_manager.register_bench(zone["bench_id"])
        print(f"[DetectionPipeline] {len(zones)} benches registered from zones.json")

    # ──────────────────────────────────────────
    # Start / Stop
    # ──────────────────────────────────────────

    def start_exam(self):
        """Called by Flask app.py when teacher clicks Start Exam."""
        self._init_camera()
        self._register_all_benches()
        self.running      = True
        self.exam_active  = True
        self.frame_number = 0
        self._start_vacant_confirmation_thread()
        if self.serial_handler:
            self.serial_handler.send_exam_start()
        else:
            print("[DetectionPipeline] Serial handler not ready — skipping Arduino signal.")
        print("[DetectionPipeline] *** EXAM STARTED ***")

    def stop_exam(self):
        """Called by Flask app.py when teacher clicks End Exam."""
        self.running     = False
        self.exam_active = False
        if self.cap:
            self.cap.release()
        if self.audit_logger:
            self.audit_logger.lock_and_hash()
        if self.serial_handler:
            self.serial_handler.send_exam_end()
        print("[DetectionPipeline] *** EXAM ENDED. Audit log locked. ***")

    # ──────────────────────────────────────────
    # Phase B — Main Detection Loop
    # ──────────────────────────────────────────

    def run(self):
        """
        Main loop — runs every frame while exam is active.
        Processing order (ARGUS v2 Phase B):
          B1  Capture frame
          B2  Pose detection        — pose_detector        (Member 2)
          B3  Zone assignment       — zone_manager         (Member 3)
          B4  Feature extraction    — feature_extractor    (Member 2)
          B5  Motion zone score     — motion_zones         (Member 3)
          B6  ML classification     — classifier           (Member 3)
          B7  Score update          — score_manager        (Member 1 — DONE)
          B8  Threshold + alert     — score_manager        (Member 1 — DONE)
          B9  MJPEG frame update    — Flask stream
          B10 Event logging         — audit_logger         (Member 4)
        """
        print("[DetectionPipeline] Detection loop running.")

        while self.running:
            loop_start = time.time()

            # B1 — Capture
            ret, frame = self.cap.read()
            if not ret:
                print("[DetectionPipeline] WARNING: Frame read failed. Retrying...")
                time.sleep(0.1)
                continue

            self.frame_number += 1
            display_frame = frame.copy()

            # B2 — Pose Detection
            # TODO (Member 2): detected_persons = self.pose_detector.detect(frame)
            # Returns: [{"landmarks": [...], "centroid": (cx, cy)}, ...]
            detected_persons = self._stub_pose_detection(frame)

            # B3 — Zone Assignment
            # TODO (Member 3): zone_assignments = self.zone_manager.assign_zones(detected_persons)
            # Returns: {person_index: bench_id or None}
            zone_assignments = self._stub_zone_assignment(detected_persons)

            # B4 + B5 — Feature Extraction + Motion Score
            # TODO (Member 2 + 3):
            # features_per_bench = self.feature_extractor.extract(
            #     detected_persons, self.prev_frame, frame,
            #     zone_assignments, self.motion_zones
            # )
            # Returns: {bench_id: {"shoulder_angle": x, "head_offset_x": x, ...}}
            features_per_bench = self._stub_feature_extraction(zone_assignments)

            # B6 — ML Classification
            # TODO (Member 3):
            # ml_results = {bench_id: self.classifier.predict(features)
            #               for bench_id, features in features_per_bench.items()}
            # Returns: {bench_id: float probability 0.0-1.0}
            ml_results = self._stub_ml_classification(features_per_bench)

            # B7 — Score Update
            self._update_scores(features_per_bench, ml_results)

            # B8 — Threshold Check + Arduino Alert
            self._check_and_alert()

            # B9 — Update MJPEG frame for Flask
            annotated = self._draw_zone_overlays(display_frame)
            with self.frame_lock:
                self.latest_frame = annotated

            # Apply decay once per second
            if time.time() - self.last_decay_time >= DECAY_INTERVAL:
                for bench_id in list(self.score_manager.bench_scores.keys()):
                    self.score_manager.apply_decay(bench_id)
                self.last_decay_time = time.time()

            self.prev_frame = frame.copy()

            # Frame rate throttle
            elapsed = time.time() - loop_start
            sleep_for = max(0.0, (1.0 / TARGET_FPS) - elapsed)
            if sleep_for > 0:
                time.sleep(sleep_for)

        print("[DetectionPipeline] Detection loop stopped.")

    # ──────────────────────────────────────────
    # B7 — Score Update Logic
    # ──────────────────────────────────────────

    def _update_scores(self, features_per_bench, ml_results):
        """
        Maps feature values to behavior types and calls score_manager.add_points().
        Full implementation requires feature_extractor.py (Member 2).
        Example of final logic:
            angle = features["shoulder_angle"]
            if angle >= config["shoulder_angle_flag"] and duration >= config["time_before_flagging"]:
                self.score_manager.add_points(bench_id, "clear_shoulder_turn", ml_prob)
        """
        for bench_id, ml_prob in ml_results.items():
            # TODO: Replace with real behavior mapping once feature_extractor is ready
            pass

    # ──────────────────────────────────────────
    # B8 — Threshold Check + Serial Alert
    # ──────────────────────────────────────────

    def _check_and_alert(self):
        """Send Arduino alert + log event when any bench crosses threshold."""
        for bench_id in list(self.score_manager.bench_scores.keys()):
            if self.score_manager.check_threshold(bench_id):
                score      = self.score_manager.get_score(bench_id)
                risk_level = self.score_manager.get_risk_level(bench_id)

                if self.serial_handler:
                    self.serial_handler.send_alert(bench_id, score, risk_level)

                if self.audit_logger:
                    self.audit_logger.log_alert(
                        bench_id     = bench_id,
                        score        = score,
                        risk_level   = risk_level,
                        frame_number = self.frame_number
                    )

    # ──────────────────────────────────────────
    # v2 Update 05 — Pending Vacant Background Thread
    # ──────────────────────────────────────────

    def _start_vacant_confirmation_thread(self):
        """v2 Update 05: Starts silent background thread for 60-sec vacancy confirmation."""
        t = threading.Thread(
            target=self._vacant_confirmation_loop,
            daemon=True,
            name="VacantConfirmationThread"
        )
        t.start()
        print("[DetectionPipeline] Vacant confirmation thread started.")

    def _vacant_confirmation_loop(self):
        while self.running:
            for bench_id in list(self.score_manager.bench_scores.keys()):
                if not self.score_manager.is_pending_vacant(bench_id):
                    continue

                # TODO (Member 3): centroid_present = self.zone_manager.get_current_occupancy(bench_id)
                centroid_present = False  # stub

                result = self.score_manager.check_vacant_confirmation(bench_id, centroid_present)

                if result == "AUTOREACTIVATED":
                    if self.audit_logger:
                        self.audit_logger.log_event(
                            action       = "AUTOREACTIVATED",
                            bench_id     = bench_id,
                            frame_number = self.frame_number
                        )
                    print(f"[VacantThread] Bench {bench_id} — AUTOREACTIVATED logged.")

                elif result == "CONFIRMED_INACTIVE":
                    if self.audit_logger:
                        self.audit_logger.log_event(
                            action       = "BENCH_CONFIRMED_INACTIVE",
                            bench_id     = bench_id,
                            frame_number = self.frame_number
                        )
                    print(f"[VacantThread] Bench {bench_id} — CONFIRMED INACTIVE logged.")

            time.sleep(1.0)

    # ──────────────────────────────────────────
    # Zone Overlay Drawing for MJPEG Stream
    # ──────────────────────────────────────────

    def _draw_zone_overlays(self, frame):
        """Colors: GREEN=low · ORANGE=medium · RED=high · GREY=inactive · ORANGE(dashed)=pending."""
        import json, os
        if not os.path.exists("data/zones.json"):
            return frame

        with open("data/zones.json", "r") as f:
            zones = json.load(f)

        color_map = {
            "LOW":    (0, 200, 0),
            "MEDIUM": (0, 165, 255),
            "HIGH":   (0, 0, 255),
        }

        for zone in zones:
            bid = zone["bench_id"]
            x1, y1, x2, y2 = zone["x1"], zone["y1"], zone["x2"], zone["y2"]

            if self.score_manager.is_inactive(bid):
                color = (150, 150, 150)
                label = f"{bid} INACTIVE"
            elif self.score_manager.is_pending_vacant(bid):
                color = (255, 165, 0)
                label = f"{bid} PENDING"
            else:
                risk  = self.score_manager.get_risk_level(bid)
                score = self.score_manager.get_score(bid)
                color = color_map.get(risk, (0, 200, 0))
                label = f"{bid} {score:.0f}pt"

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1 + 4, y1 + 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

        return frame

    # ──────────────────────────────────────────
    # Stubs — replace with real calls as each file is completed
    # ──────────────────────────────────────────

    def _stub_pose_detection(self, frame):
        return []

    def _stub_zone_assignment(self, detected_persons):
        return {}

    def _stub_feature_extraction(self, zone_assignments):
        return {}

    def _stub_ml_classification(self, features_per_bench):
        return {}

    # ──────────────────────────────────────────
    # Flask Integration — called from app.py
    # ──────────────────────────────────────────

    def get_latest_frame(self):
        """Thread-safe frame getter for Flask MJPEG stream."""
        with self.frame_lock:
            return self.latest_frame

    def get_score_data(self):
        """All bench scores for Flask dashboard API — called every second."""
        return self.score_manager.get_all_scores()

    def get_top_benches(self, n=3):
        """Top N riskiest benches for Arduino LCD STATUS message."""
        return self.score_manager.get_top_benches(n)

    def reset_bench(self, bench_id, reason, contradiction_flag=False):
        """Called from Flask management route — teacher resets a bench mid-exam."""
        self.score_manager.reset_bench(
            bench_id, reason=reason, contradiction_flag=contradiction_flag
        )

    def remove_bench(self, bench_id, reason):
        """Called from Flask management route — teacher removes a bench mid-exam."""
        self.score_manager.remove_bench(bench_id, reason=reason)


# ─────────────────────────────────────────────
# Singleton — shared between this module and Flask app.py
# ─────────────────────────────────────────────

pipeline = DetectionPipeline()


if __name__ == "__main__":
    print("=" * 55)
    print("ARGUS v2 DetectionPipeline — Smoke Test")
    print("=" * 55)
    p = DetectionPipeline()
    print(f"ScoreManager ready : {p.score_manager is not None}")
    print(f"Running state      : {p.running}")
    print(f"Stubs active       : pose={p.pose_detector}, zones={p.zone_manager}, ml={p.classifier}")
    print("\n[OK] Pipeline initialized. Start exam via Flask dashboard.")
