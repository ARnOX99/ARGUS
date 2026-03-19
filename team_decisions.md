# ARGUS — Team Decisions Document
All agreed values, weights, and thresholds for the ARGUS project.
Every member must follow these exact values in their code.
Last updated: Week 1

---

## Suspicion Score Weights

| Behavior | Trigger Condition | Points Added |
|---|---|---|
| Slight shoulder turn | Angle 10-20 deg, under 2 sec | +2 |
| Clear shoulder turn | Angle 20+ deg, 2+ seconds | +6 |
| Sustained body turn | Angle 25+ deg, 5+ seconds | +10 |
| Coarse head turn | Nose offset >20% shoulder width | +3 |
| Arm extended sideways | Wrist displacement >40% torso width | +5 |
| Sudden fast wrist move | Wrist velocity above threshold | +4 |
| High zone motion | Motion score >0.15 | +2 |
| Combined: turn + wrist | Both triggers simultaneously | +12 |
| ML high confidence | RF probability >0.80 | x1.5 multiplier |

## Score Decay
| Condition | Decay |
|---|---|
| Calm period — 30 seconds | -1 point |
| Extended calm — 5 minutes | -5 points reset |

---

## Alert Thresholds by Exam Mode

| Parameter | LENIENT | STANDARD | STRICT |
|---|---|---|---|
| Alert threshold | 50 points | 30 points | 15 points |
| Shoulder angle flag | 35 degrees | 25 degrees | 15 degrees |
| Time before flagging | 4 seconds | 2 seconds | 1 second |
| Motion sensitivity | High only | Medium | Any |
| ML confidence threshold | 0.80 | 0.65 | 0.50 |
| Score decay rate | -3 per minute | -1 per minute | -0.3 per minute |
| Combined behavior multiplier | 1.2x | 1.5x | 2.0x |

---

## 7 Features (feature_extractor.py)

| Feature | Suspicious Threshold |
|---|---|
| shoulder_angle | >20 degrees for 2+ seconds |
| head_offset_x | >0.20 (20% of shoulder width) |
| head_offset_y | >0.15 |
| left_wrist_dist | >0.40 |
| right_wrist_dist | >0.40 |
| wrist_velocity_avg | >configurable threshold |
| zone_motion_score | >0.15 |

---

## ML Model
- Model type: Random Forest
- Number of estimators: 100
- Input: 7 features above
- Output: 0 (normal) or 1 (suspicious)
- Target accuracy: 85%+
- Saved as: model/classifier.pkl

---

## Key Landmarks Used (MediaPipe Pose)
| Landmark | Index | Purpose |
|---|---|---|
| Nose | 0 | Head direction |
| Left Ear | 7 | Head orientation |
| Right Ear | 8 | Head orientation |
| Left Shoulder | 11 | Shoulder angle |
| Right Shoulder | 12 | Shoulder angle |
| Left Wrist | 15 | Arm extension |
| Right Wrist | 16 | Arm extension |
| Left Hip | 23 | Zone centroid |
| Right Hip | 24 | Zone centroid |

---

## Coding Standards
- Language: Python 3.9+
- All files follow names exactly as in project blueprint
- Every function must have a one-line comment explaining what it does
- No hardcoded values — all thresholds read from config.json
- All code pushed to GitHub with clear commit messages

---

## Member Responsibilities (Quick Reference)
| Member | Primary File |
|---|---|
| Member 1 (Lead) | score_manager.py, main_detection.py, app.py |
| Member 2 | pose_detector.py, feature_extractor.py, dashboard pages |
| Member 3 | motion_zones.py, zone_manager.py, classifier.py, train_model.py |
| Member 4 | console.ino, serial_handler.py, audit_logger.py |
| Member 5 | Documentation, data labeling, testing records, presentation |
