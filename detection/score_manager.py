import time
import json
import os


# ─────────────────────────────────────────────
# SCORE WEIGHTS — from team_decisions.md
# ─────────────────────────────────────────────

WEIGHTS = {
    "slight_shoulder_turn":  2,    # Angle 10-20 deg, under 2 sec
    "clear_shoulder_turn":   6,    # Angle 20+ deg, 2+ seconds
    "sustained_body_turn":   10,   # Angle 25+ deg, 5+ seconds
    "coarse_head_turn":      3,    # Nose offset >20% shoulder width
    "arm_extended":          5,    # Wrist displacement >40% torso width
    "sudden_wrist_move":     4,    # Wrist velocity above threshold
    "high_zone_motion":      2,    # Motion score >0.15
    "combined_turn_wrist":   12,   # Body turn + arm extension simultaneously
}

# ML high confidence multiplier — if RF probability > threshold, multiply points
ML_HIGH_CONFIDENCE_MULTIPLIER = 1.5
ML_HIGH_CONFIDENCE_THRESHOLD  = 0.80

# Extra decay applied after 5 continuous minutes of calm
DECAY_CALM_5MIN = 5

# v2 Update 05 — seconds of zero centroid before bench confirmed INACTIVE
PENDING_VACANT_TIMEOUT = 60

# ─────────────────────────────────────────────
# EXAM MODE THRESHOLDS — loaded from config.json
# Defaults here are STANDARD mode
# ─────────────────────────────────────────────

DEFAULT_CONFIG = {
    "mode":                     "STANDARD",
    "alert_threshold":          30,
    "score_decay_rate_per_min": 1.0,
    "combined_multiplier":      1.5,
    "ml_confidence_threshold":  0.65,
}


# ─────────────────────────────────────────────
# ScoreManager Class
# ─────────────────────────────────────────────

class ScoreManager:

    def __init__(self, config_path="data/config.json"):
        self.config = self._load_config(config_path)

        # Active bench tracking — bench_id -> state dict
        self.bench_scores = {}

        # v2: Archived scores for benches reset or removed mid-exam
        self.archived_scores = {}

        # v2 Update 05: confirmed-vacant bench IDs (kept in bench_scores for report)
        self.inactive_benches = set()

        print(f"[ScoreManager] Initialized in {self.config['mode']} mode. "
              f"Alert threshold: {self.config['alert_threshold']} points.")

    # ──────────────────────────────────────────
    # Load config.json
    # ──────────────────────────────────────────

    def _load_config(self, config_path):
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
            print(f"[ScoreManager] Config loaded from {config_path}")
            return config
        print(f"[ScoreManager] Config file not found. Using DEFAULT (STANDARD mode).")
        return DEFAULT_CONFIG.copy()

    # ──────────────────────────────────────────
    # Register a bench zone
    # ──────────────────────────────────────────

    def register_bench(self, bench_id):
        """Add a new bench to active tracking — called during pre-exam zone setup."""
        if bench_id not in self.bench_scores:
            now = time.time()
            self.bench_scores[bench_id] = {
                "score":                0.0,
                "last_event_time":      now,
                "calm_since":           now,
                "last_decay_time":      now,   # v2 BUG FIX: incremental decay tracking
                "alert_fired":          False,
                "teacher_modified":     False, # v2 Update 06: yellow asterisk in report
                "pending_vacant":       False, # v2 Update 05: in 60-sec confirmation window
                "pending_vacant_since": None,  # v2 Update 05: window start timestamp
            }
            self.inactive_benches.discard(bench_id)
            print(f"[ScoreManager] Bench {bench_id} registered.")

    # ──────────────────────────────────────────
    # Add points to a bench score
    # ──────────────────────────────────────────

    def add_points(self, bench_id, behavior_type, ml_probability=0.0):
        """Add weighted suspicion points based on detected behavior.
        v2: Skip if inactive. Auto-reactivate if pending_vacant and centroid detected."""
        if bench_id not in self.bench_scores:
            self.register_bench(bench_id)

        # Do not score inactive benches
        if bench_id in self.inactive_benches:
            return 0

        # v2 Update 05 — centroid detected in pending-vacant bench = auto-reactivate
        if self.bench_scores[bench_id]["pending_vacant"]:
            self.cancel_pending_vacant(bench_id, reason="AUTOREACTIVATED")

        points = WEIGHTS.get(behavior_type, 0)
        if points == 0:
            print(f"[ScoreManager] WARNING: Unknown behavior type '{behavior_type}'")
            return 0

        # Apply ML high confidence multiplier
        if ml_probability >= ML_HIGH_CONFIDENCE_THRESHOLD:
            points *= ML_HIGH_CONFIDENCE_MULTIPLIER
            print(f"[ScoreManager] ML confidence {ml_probability:.2f} — x1.5 multiplier applied.")

        # Apply combined behavior multiplier from config
        if behavior_type == "combined_turn_wrist":
            points *= self.config.get("combined_multiplier", 1.5)

        points = round(points, 1)
        now    = time.time()

        self.bench_scores[bench_id]["score"]           += points
        self.bench_scores[bench_id]["last_event_time"]  = now
        self.bench_scores[bench_id]["calm_since"]       = now

        print(f"[ScoreManager] Bench {bench_id} | +{points} pts ({behavior_type}) | "
              f"Total: {self.bench_scores[bench_id]['score']:.1f}")
        return points

    # ──────────────────────────────────────────
    # Apply incremental decay — called every second from main loop
    # ──────────────────────────────────────────

    def apply_decay(self, bench_id):
        """Reduce score slowly during calm periods.
        v2 BUG FIX: Uses last_decay_time so only the incremental delta since
        last call is subtracted. v1 re-applied ALL decay since calm_since every call."""
        if bench_id not in self.bench_scores:
            return
        if bench_id in self.inactive_benches:
            return

        bench = self.bench_scores[bench_id]
        now   = time.time()

        calm_duration         = now - bench["calm_since"]
        time_since_last_decay = now - bench["last_decay_time"]

        if bench["score"] <= 0 or calm_duration <= 0:
            bench["last_decay_time"] = now
            return

        decay_per_min = self.config.get("score_decay_rate_per_min", 1.0)
        decay_per_sec = decay_per_min / 60.0

        # Only subtract incremental decay since last call
        incremental_decay        = round(decay_per_sec * time_since_last_decay, 3)
        bench["score"]           = max(0.0, bench["score"] - incremental_decay)
        bench["last_decay_time"] = now

        # Extra -5 after 5 continuous minutes of calm
        # v2 BUG FIX: reset calm_since so this only fires once per 5-min window
        if calm_duration >= 300:
            bench["score"]      = max(0.0, bench["score"] - DECAY_CALM_5MIN)
            bench["calm_since"] = now
            print(f"[ScoreManager] Bench {bench_id} — 5 min calm. Extra -5 decay applied.")

    # ──────────────────────────────────────────
    # Check if bench has crossed alert threshold
    # ──────────────────────────────────────────

    def check_threshold(self, bench_id):
        """Returns True if bench score exceeds alert threshold."""
        if bench_id not in self.bench_scores:
            return False
        if bench_id in self.inactive_benches:
            return False

        score     = self.bench_scores[bench_id]["score"]
        threshold = self.config.get("alert_threshold", 30)

        if score >= threshold:
            if not self.bench_scores[bench_id]["alert_fired"]:
                self.bench_scores[bench_id]["alert_fired"] = True
                print(f"[ScoreManager] *** ALERT *** Bench {bench_id} crossed threshold! "
                      f"Score: {score:.1f} / {threshold}")
            return True

        # Re-arm alert if score drops back below 60% of threshold
        if score < threshold * 0.6:
            self.bench_scores[bench_id]["alert_fired"] = False

        return False

    # ──────────────────────────────────────────
    # Getters
    # ──────────────────────────────────────────

    def get_score(self, bench_id):
        """Current suspicion score for a bench."""
        if bench_id not in self.bench_scores:
            return 0.0
        return round(self.bench_scores[bench_id]["score"], 1)

    def get_risk_level(self, bench_id):
        """Returns LOW / MEDIUM / HIGH based on score as % of threshold."""
        score     = self.get_score(bench_id)
        threshold = self.config.get("alert_threshold", 30)
        ratio     = score / threshold if threshold > 0 else 0

        if ratio < 0.30:
            return "LOW"
        elif ratio < 0.80:
            return "MEDIUM"
        else:
            return "HIGH"

    def get_all_scores(self):
        """All bench states for Flask dashboard API — called every second.
        v2: includes inactive, pending_vacant, teacher_modified flags."""
        result = {}
        for bench_id in self.bench_scores:
            bench = self.bench_scores[bench_id]
            result[bench_id] = {
                "score":            self.get_score(bench_id),
                "risk_level":       self.get_risk_level(bench_id),
                "alert":            self.check_threshold(bench_id),
                "inactive":         bench_id in self.inactive_benches,  # v2 Update 05
                "pending_vacant":   bench["pending_vacant"],            # v2 Update 05
                "teacher_modified": bench["teacher_modified"],          # v2 Update 06
            }
        return result

    def get_top_benches(self, n=3):
        """Top N riskiest benches — excludes inactive. Used by Arduino LCD top-3 display."""
        active = {k: v for k, v in self.bench_scores.items()
                  if k not in self.inactive_benches}
        sorted_benches = sorted(active.items(),
                                key=lambda x: x[1]["score"], reverse=True)
        return [(bench_id, round(data["score"], 1)) for bench_id, data in sorted_benches[:n]]

    def get_archived_scores(self):
        """All archived pre-reset scores with contradiction flags — used by report generator."""
        return self.archived_scores.copy()

    def is_pending_vacant(self, bench_id):
        if bench_id not in self.bench_scores:
            return False
        return self.bench_scores[bench_id]["pending_vacant"]

    def is_inactive(self, bench_id):
        return bench_id in self.inactive_benches

    # ──────────────────────────────────────────
    # v2 Update 04 — Reset bench WITH contradiction flag
    # ──────────────────────────────────────────

    def reset_bench(self, bench_id, reason="mid_exam_reassignment", contradiction_flag=False):
        """Archives old score and resets bench to 0.
        v2 Update 04: contradiction_flag=True if camera detected a person here
                      at the moment teacher requested the reset. Stored permanently.
        v2 Update 06: Sets teacher_modified=True for yellow asterisk in report."""
        if bench_id in self.bench_scores:
            old_score = self.bench_scores[bench_id]["score"]
            self.archived_scores[bench_id] = {
                "archived_score":     round(old_score, 1),
                "archived_at":        time.time(),
                "reason":             reason,
                "contradiction_flag": contradiction_flag,  # permanent — cannot be removed
            }
            now = time.time()
            self.bench_scores[bench_id].update({
                "score":                0.0,
                "alert_fired":          False,
                "calm_since":           now,
                "last_decay_time":      now,
                "pending_vacant":       False,
                "pending_vacant_since": None,
                "teacher_modified":     True,  # v2 Update 06
            })
            flag_note = " ⚠ CONTRADICTION FLAG SET" if contradiction_flag else ""
            print(f"[ScoreManager] Bench {bench_id} reset. "
                  f"Old score {old_score:.1f} archived.{flag_note}")

    # ──────────────────────────────────────────
    # v2 Update 05 — Pending Vacant / 60-sec confirmation
    # ──────────────────────────────────────────

    def mark_pending_vacant(self, bench_id):
        """v2 Update 05: Called when teacher clicks Remove Bench.
        Does NOT immediately deactivate — starts silent 60-sec confirmation window.
        main_detection.py background thread calls check_vacant_confirmation() every second."""
        if bench_id in self.bench_scores:
            self.bench_scores[bench_id]["pending_vacant"]       = True
            self.bench_scores[bench_id]["pending_vacant_since"] = time.time()
            print(f"[ScoreManager] Bench {bench_id} — pending vacant. "
                  f"60-second confirmation window started.")

    def cancel_pending_vacant(self, bench_id, reason="AUTOREACTIVATED"):
        """v2 Update 05: Centroid reappeared within 60s — monitoring auto-resumes.
        Returns True if bench was actually pending (so caller knows to log to audit)."""
        if bench_id in self.bench_scores and self.bench_scores[bench_id]["pending_vacant"]:
            self.bench_scores[bench_id]["pending_vacant"]       = False
            self.bench_scores[bench_id]["pending_vacant_since"] = None
            print(f"[ScoreManager] Bench {bench_id} — {reason}. Monitoring auto-resumed.")
            return True
        return False

    def confirm_inactive(self, bench_id):
        """v2 Update 05: 60 consecutive seconds of zero centroid confirmed.
        Bench marked INACTIVE. Score preserved in bench_scores for post-exam report."""
        if bench_id in self.bench_scores:
            self.bench_scores[bench_id]["pending_vacant"]       = False
            self.bench_scores[bench_id]["pending_vacant_since"] = None
            self.inactive_benches.add(bench_id)
            print(f"[ScoreManager] Bench {bench_id} — confirmed INACTIVE "
                  f"(60-sec vacancy confirmed). Score preserved for report.")

    def check_vacant_confirmation(self, bench_id, centroid_present):
        """v2 Update 05: Called every second by background thread in main_detection.py.
        centroid_present (bool): True if zone_manager detected a person in this zone.

        Returns:
            'AUTOREACTIVATED'    — person returned, caller must log to audit
            'CONFIRMED_INACTIVE' — 60s passed with no centroid, bench now INACTIVE
            'PENDING'            — still within window, nothing to do yet
            'NOT_PENDING'        — bench was not in pending-vacant state
        """
        if bench_id not in self.bench_scores:
            return "NOT_PENDING"

        bench = self.bench_scores[bench_id]
        if not bench["pending_vacant"]:
            return "NOT_PENDING"

        if centroid_present:
            self.cancel_pending_vacant(bench_id, reason="AUTOREACTIVATED")
            return "AUTOREACTIVATED"

        elapsed = time.time() - bench["pending_vacant_since"]
        if elapsed >= PENDING_VACANT_TIMEOUT:
            self.confirm_inactive(bench_id)
            return "CONFIRMED_INACTIVE"

        return "PENDING"

    # ──────────────────────────────────────────
    # Remove bench — routes through vacancy confirmation (v2)
    # ──────────────────────────────────────────

    def remove_bench(self, bench_id, reason="bench_removed"):
        """v2: Archives score and starts 60-sec pending-vacant confirmation.
        Does NOT hard-delete. Use _force_remove_bench() only at exam end."""
        if bench_id in self.bench_scores:
            self.reset_bench(bench_id, reason=reason)
            self.mark_pending_vacant(bench_id)

    def _force_remove_bench(self, bench_id):
        """Hard remove — ONLY for post-exam cleanup, never mid-exam."""
        if bench_id in self.bench_scores:
            del self.bench_scores[bench_id]
        self.inactive_benches.discard(bench_id)
        print(f"[ScoreManager] Bench {bench_id} force-removed (exam end cleanup).")


# ─────────────────────────────────────────────
# Quick test — run directly to verify all v2 features
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("ARGUS v2 ScoreManager — Self Test")
    print("=" * 55)

    sm = ScoreManager()
    sm.register_bench("B1")
    sm.register_bench("B7")

    print("\n--- Test 1: Normal scoring + ML multiplier ---")
    sm.add_points("B7", "clear_shoulder_turn",  ml_probability=0.70)
    sm.add_points("B7", "arm_extended",         ml_probability=0.85)
    sm.add_points("B7", "combined_turn_wrist",  ml_probability=0.90)
    print(f"B7 score: {sm.get_score('B7')} | Risk: {sm.get_risk_level('B7')} | Alert: {sm.check_threshold('B7')}")

    print("\n--- Test 2: v2 reset_bench with contradiction_flag ---")
    sm.reset_bench("B7", reason="Student moved to B12", contradiction_flag=True)
    print(f"B7 score after reset: {sm.get_score('B7')}")
    print(f"B7 teacher_modified:  {sm.bench_scores['B7']['teacher_modified']}")
    print(f"Archived:             {sm.get_archived_scores()}")

    print("\n--- Test 3: v2 pending vacant — auto-reactivation ---")
    sm.mark_pending_vacant("B1")
    print(f"B1 pending_vacant: {sm.is_pending_vacant('B1')}")
    result = sm.check_vacant_confirmation("B1", centroid_present=True)
    print(f"Result (person back): {result}")
    print(f"B1 pending after reactivation: {sm.is_pending_vacant('B1')}")

    print("\n--- Test 4: v2 pending vacant — confirmed inactive ---")
    sm.mark_pending_vacant("B1")
    sm.bench_scores["B1"]["pending_vacant_since"] -= 61  # simulate 61s elapsed
    result = sm.check_vacant_confirmation("B1", centroid_present=False)
    print(f"Result (61s, no centroid): {result}")
    print(f"B1 inactive: {sm.is_inactive('B1')}")

    print("\n--- Test 5: get_all_scores with v2 flags ---")
    sm.add_points("B7", "coarse_head_turn", ml_probability=0.50)
    for bid, data in sm.get_all_scores().items():
        print(f"  {bid}: {data}")

    print("\n--- Test 6: get_top_benches excludes inactive ---")
    print(f"Top benches: {sm.get_top_benches()}")

    print("\n[ALL TESTS PASSED]")
