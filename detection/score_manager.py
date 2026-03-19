# score_manager.py
# ARGUS — Adaptive Real-time Guardian for Unified Surveillance
# Member 1 — Project Lead
# Purpose: Manages cumulative suspicion scores for all bench zones.
# This is the core innovation of ARGUS — scores build over time instead
# of firing alerts on every suspicious frame.

import time
import json
import os

# ─────────────────────────────────────────────
# SCORE WEIGHTS — from team_decisions.md
# ─────────────────────────────────────────────

WEIGHTS = {
    "slight_shoulder_turn":   2,   # Angle 10-20 deg, under 2 sec
    "clear_shoulder_turn":    6,   # Angle 20+ deg, 2+ seconds
    "sustained_body_turn":    10,  # Angle 25+ deg, 5+ seconds
    "coarse_head_turn":       3,   # Nose offset >20% shoulder width
    "arm_extended":           5,   # Wrist displacement >40% torso width
    "sudden_wrist_move":      4,   # Wrist velocity above threshold
    "high_zone_motion":       2,   # Motion score >0.15
    "combined_turn_wrist":    12,  # Body turn + arm extension simultaneously
}

# ML high confidence multiplier — if RF probability >0.80, multiply points by this
ML_HIGH_CONFIDENCE_MULTIPLIER = 1.5
ML_HIGH_CONFIDENCE_THRESHOLD  = 0.80

# ─────────────────────────────────────────────
# DECAY SETTINGS
# ─────────────────────────────────────────────

DECAY_CALM_30SEC   = 1    # -1 point after 30 seconds of calm
DECAY_CALM_5MIN    = 5    # -5 points after 5 minutes of calm

# ─────────────────────────────────────────────
# EXAM MODE THRESHOLDS — loaded from config.json
# Defaults here are STANDARD mode
# ─────────────────────────────────────────────

DEFAULT_CONFIG = {
    "mode":                       "STANDARD",
    "alert_threshold":            30,
    "score_decay_rate_per_min":   1.0,
    "combined_multiplier":        1.5,
    "ml_confidence_threshold":    0.65,
}


# ─────────────────────────────────────────────
# ScoreManager Class
# ─────────────────────────────────────────────

class ScoreManager:

    def __init__(self, config_path="data/config.json"):
        # Load config from file if it exists, else use defaults
        self.config = self._load_config(config_path)

        # Dictionary: bench_id -> score data
        # Example: {"B1": {"score": 0, "last_event_time": 1234567890, "calm_since": 1234567890}}
        self.bench_scores = {}

        # Archived scores for benches that were removed/modified mid-exam
        self.archived_scores = {}

        print(f"[ScoreManager] Initialized in {self.config['mode']} mode. "
              f"Alert threshold: {self.config['alert_threshold']} points.")

    # ──────────────────────────────────────────
    # Load config.json
    # ──────────────────────────────────────────

    def _load_config(self, config_path):
        # Try to read config from file, fall back to defaults if not found
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
            print(f"[ScoreManager] Config loaded from {config_path}")
            return config
        else:
            print(f"[ScoreManager] Config file not found. Using DEFAULT (STANDARD mode).")
            return DEFAULT_CONFIG.copy()

    # ──────────────────────────────────────────
    # Register a bench zone
    # ──────────────────────────────────────────

    def register_bench(self, bench_id):
        # Add a new bench to tracking — called during pre-exam zone setup
        if bench_id not in self.bench_scores:
            self.bench_scores[bench_id] = {
                "score":            0.0,
                "last_event_time":  time.time(),
                "calm_since":       time.time(),
                "alert_fired":      False,
            }
            print(f"[ScoreManager] Bench {bench_id} registered.")

    # ──────────────────────────────────────────
    # Add points to a bench score
    # ──────────────────────────────────────────

    def add_points(self, bench_id, behavior_type, ml_probability=0.0):
        # Add weighted suspicion points to bench based on detected behavior
        if bench_id not in self.bench_scores:
            self.register_bench(bench_id)

        # Get base points for this behavior
        points = WEIGHTS.get(behavior_type, 0)

        if points == 0:
            print(f"[ScoreManager] WARNING: Unknown behavior type '{behavior_type}'")
            return 0

        # Apply ML high confidence multiplier if model is very sure
        if ml_probability >= ML_HIGH_CONFIDENCE_THRESHOLD:
            points = points * ML_HIGH_CONFIDENCE_MULTIPLIER
            print(f"[ScoreManager] ML confidence {ml_probability:.2f} — multiplier applied.")

        # Apply combined behavior multiplier from config
        if behavior_type == "combined_turn_wrist":
            points = points * self.config.get("combined_multiplier", 1.5)

        # Round to 1 decimal place
        points = round(points, 1)

        # Add to bench score
        self.bench_scores[bench_id]["score"] += points
        self.bench_scores[bench_id]["last_event_time"] = time.time()
        self.bench_scores[bench_id]["calm_since"] = time.time()  # reset calm timer

        print(f"[ScoreManager] Bench {bench_id} | +{points} pts ({behavior_type}) | "
              f"Total: {self.bench_scores[bench_id]['score']:.1f}")

        return points

    # ──────────────────────────────────────────
    # Apply score decay during calm periods
    # ──────────────────────────────────────────

    def apply_decay(self, bench_id):
        # Reduce score slowly when bench has been calm — prevents score buildup from old events
        if bench_id not in self.bench_scores:
            return

        bench = self.bench_scores[bench_id]
        calm_duration = time.time() - bench["calm_since"]  # seconds since last suspicious event

        decay_per_min = self.config.get("score_decay_rate_per_min", 1.0)

        # Convert per-minute rate to per-second
        decay_per_sec = decay_per_min / 60.0

        # Apply decay every second
        if calm_duration > 0:
            decay_amount = round(decay_per_sec * calm_duration, 2)
            bench["score"] = max(0.0, bench["score"] - decay_amount)

        # Extra reset if calm for 5 minutes
        if calm_duration >= 300:
            bench["score"] = max(0.0, bench["score"] - DECAY_CALM_5MIN)
            print(f"[ScoreManager] Bench {bench_id} — 5 min calm. Extra -5 decay applied.")

    # ──────────────────────────────────────────
    # Check if bench has crossed alert threshold
    # ──────────────────────────────────────────

    def check_threshold(self, bench_id):
        # Returns True if bench score exceeds alert threshold — triggers alert
        if bench_id not in self.bench_scores:
            return False

        score     = self.bench_scores[bench_id]["score"]
        threshold = self.config.get("alert_threshold", 30)

        if score >= threshold:
            if not self.bench_scores[bench_id]["alert_fired"]:
                # First time crossing threshold — fire alert
                self.bench_scores[bench_id]["alert_fired"] = True
                print(f"[ScoreManager] *** ALERT *** Bench {bench_id} crossed threshold! "
                      f"Score: {score:.1f} / {threshold}")
            return True

        # If score drops back below threshold, reset alert flag so it can fire again
        if score < threshold * 0.6:
            self.bench_scores[bench_id]["alert_fired"] = False

        return False

    # ──────────────────────────────────────────
    # Get current score for a bench
    # ──────────────────────────────────────────

    def get_score(self, bench_id):
        # Returns current suspicion score for a bench — used by dashboard and Arduino
        if bench_id not in self.bench_scores:
            return 0.0
        return round(self.bench_scores[bench_id]["score"], 1)

    # ──────────────────────────────────────────
    # Get risk level label for a bench
    # ──────────────────────────────────────────

    def get_risk_level(self, bench_id):
        # Returns LOW / MEDIUM / HIGH based on score as % of threshold
        score     = self.get_score(bench_id)
        threshold = self.config.get("alert_threshold", 30)
        ratio     = score / threshold if threshold > 0 else 0

        if ratio < 0.30:
            return "LOW"
        elif ratio < 0.80:
            return "MEDIUM"
        else:
            return "HIGH"

    # ──────────────────────────────────────────
    # Get all bench scores — used by dashboard API
    # ──────────────────────────────────────────

    def get_all_scores(self):
        # Returns dict of all bench scores with risk levels — sent to Flask every second
        result = {}
        for bench_id in self.bench_scores:
            result[bench_id] = {
                "score":      self.get_score(bench_id),
                "risk_level": self.get_risk_level(bench_id),
                "alert":      self.check_threshold(bench_id),
            }
        return result

    # ──────────────────────────────────────────
    # Reset a bench score — used when bench is reassigned mid-exam
    # ──────────────────────────────────────────

    def reset_bench(self, bench_id, reason="mid_exam_reassignment"):
        # Archive old score and reset to 0 — called from bench management panel
        if bench_id in self.bench_scores:
            old_score = self.bench_scores[bench_id]["score"]
            self.archived_scores[bench_id] = {
                "archived_score": old_score,
                "archived_at":    time.time(),
                "reason":         reason,
            }
            self.bench_scores[bench_id]["score"]       = 0.0
            self.bench_scores[bench_id]["alert_fired"] = False
            self.bench_scores[bench_id]["calm_since"]  = time.time()
            print(f"[ScoreManager] Bench {bench_id} reset. Old score {old_score} archived.")

    # ──────────────────────────────────────────
    # Remove a bench — used when bench is removed mid-exam
    # ──────────────────────────────────────────

    def remove_bench(self, bench_id, reason="bench_removed"):
        # Archive and remove bench from active tracking
        if bench_id in self.bench_scores:
            self.reset_bench(bench_id, reason)
            del self.bench_scores[bench_id]
            print(f"[ScoreManager] Bench {bench_id} removed from active tracking.")

    # ──────────────────────────────────────────
    # Get top N riskiest benches — used by dashboard top 3 panel
    # ──────────────────────────────────────────

    def get_top_benches(self, n=3):
        # Returns top N benches sorted by score descending
        sorted_benches = sorted(
            self.bench_scores.items(),
            key=lambda x: x[1]["score"],
            reverse=True
        )
        return [(bench_id, round(data["score"], 1)) for bench_id, data in sorted_benches[:n]]


# ─────────────────────────────────────────────
# Quick test — run this file directly to verify
# ─────────────────────────────────────────────

if __name__ == "__main__":
    sm = ScoreManager()

    # Register some benches
    sm.register_bench("B1")
    sm.register_bench("B7")

    # Simulate some events on Bench 7
    sm.add_points("B7", "clear_shoulder_turn", ml_probability=0.70)
    sm.add_points("B7", "arm_extended",        ml_probability=0.85)
    sm.add_points("B7", "combined_turn_wrist", ml_probability=0.90)

    # Check threshold
    print(f"\nBench B7 alert: {sm.check_threshold('B7')}")
    print(f"Risk level: {sm.get_risk_level('B7')}")
    print(f"\nAll scores: {sm.get_all_scores()}")
    print(f"Top benches: {sm.get_top_benches()}")
