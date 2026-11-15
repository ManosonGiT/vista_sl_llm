"""
Convert MediaPipe hand keyframes (from /api/v1/game/target/{lessonTitle})
into human-readable descriptions of how a sign is performed.

MediaPipe hand landmark indices:
  0 wrist
  1-4  thumb  (CMC, MCP, IP, TIP)
  5-8  index  (MCP, PIP, DIP, TIP)
  9-12 middle, 13-16 ring, 17-20 pinky
Coordinates are normalised to the video frame: x right, y DOWN, z towards camera (negative = closer).
"""
import math
import os
import subprocess

FINGERS = {
    "thumb": (1, 2, 3, 4),
    "index": (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring": (13, 14, 15, 16),
    "pinky": (17, 18, 19, 20),
}

# ---------- geometry helpers ----------

def _v(a, b):
    return (b["x"] - a["x"], b["y"] - a["y"], b["z"] - a["z"])

def _dist(a, b):
    return math.sqrt(sum(c * c for c in _v(a, b)))

def _angle(a, b, c):
    """Angle at b (degrees) between segments b->a and b->c. 180 = straight."""
    v1, v2 = _v(b, a), _v(b, c)
    n1 = math.sqrt(sum(x * x for x in v1)) or 1e-9
    n2 = math.sqrt(sum(x * x for x in v2)) or 1e-9
    cos = sum(x * y for x, y in zip(v1, v2)) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))

def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

# ---------- per-hand features ----------

def finger_state(lm, name):
    j = FINGERS[name]
    if name == "thumb":
        bend = _angle(lm[j[0]], lm[j[1]], lm[j[2]]) + _angle(lm[j[1]], lm[j[2]], lm[j[3]])
        bend /= 2
        # thumb counts as extended if its tip is far from the index base
        far = _dist(lm[4], lm[5]) > 0.6 * _dist(lm[0], lm[5])
        if bend > 155 and far:
            return "extended"
        if bend > 125:
            return "half-bent"
        return "folded"
    pip = _angle(lm[j[0]], lm[j[1]], lm[j[2]])
    dip = _angle(lm[j[1]], lm[j[2]], lm[j[3]])
    avg = (pip + dip) / 2
    if avg > 160:
        return "extended"
    if avg > 110:
        return "bent"
    return "curled"

def palm_orientation(lm, handedness):
    """Approximate palm facing direction (camera view)."""
    n = _cross(_v(lm[0], lm[5]), _v(lm[0], lm[17]))
    if handedness == "Left":  # MediaPipe mirrors; flip normal for left hand
        n = tuple(-c for c in n)
    ax = max(range(3), key=lambda i: abs(n[i]))
    if ax == 2:
        return "palm facing the viewer" if n[2] < 0 else "palm facing the signer"
    if ax == 1:
        return "palm facing down" if n[1] > 0 else "palm facing up"
    return "palm facing sideways"

def pointing_direction(lm):
    d = _v(lm[0], lm[9])  # wrist -> middle MCP
    ax = 0 if abs(d[0]) > abs(d[1]) else 1
    if ax == 1:
        return "fingers pointing up" if d[1] < 0 else "fingers pointing down"
    return "fingers pointing sideways"

def location(lm):
    top_y = min(p["y"] for p in lm)
    vert = "head/face level" if top_y < 0.48 else "chest/shoulder level" if top_y < 0.70 else "waist level"
    return vert

def contacts(lm):
    scale = _dist(lm[0], lm[9]) or 1e-9
    out = []
    for name, tip in (("index", 8), ("middle", 12), ("ring", 16), ("pinky", 20)):
        if _dist(lm[4], lm[tip]) / scale < 0.35:
            out.append(f"thumb tip touches {name} tip")
    names = ["index", "middle", "ring", "pinky"]
    tips = [8, 12, 16, 20]
    ext = [finger_state(lm, n) == "extended" for n in names]
    together = [ext[i] and ext[i + 1] and _dist(lm[tips[i]], lm[tips[i + 1]]) / scale < 0.25 for i in range(3)]
    if all(ext) and all(together):
        out.append("all four fingers extended and pressed together (no gaps)")
    elif all(ext) and not any(together):
        out.append("all four fingers extended and spread apart")
    else:
        for i in range(3):
            if together[i]:
                out.append(f"{names[i]} and {names[i + 1]} extended and touching")
    return out

def handshape_name(states):
    ext = [f for f, s in states.items() if s == "extended"]
    ext_set = set(ext)
    if not ext or ext_set == {"thumb"} and states["index"] == "curled":
        return "closed fist" + (" with thumb out" if "thumb" in ext_set else "")
    if ext_set >= {"index", "middle", "ring", "pinky"}:
        return "open flat hand" + (" (thumb out)" if "thumb" in ext_set else " (thumb tucked)")
    if ext_set - {"thumb"} == {"index"}:
        return "index finger pointing" + (" (L-shape with thumb)" if "thumb" in ext_set else "")
    if ext_set - {"thumb"} == {"index", "middle"}:
        return "two fingers (V / index+middle)"
    if ext_set - {"thumb"} == {"pinky"}:
        return "pinky extended" + (" with thumb (Y-shape)" if "thumb" in ext_set else "")
    if ext_set - {"thumb"} == {"index", "middle", "ring"}:
        return "three fingers (index, middle, ring)"
    return "extended: " + ", ".join(ext)

def describe_hand(hand, label="Dominant hand"):
    lm = hand["landmarks"]
    side = hand.get("handedness", "?")
    states = {f: finger_state(lm, f) for f in FINGERS}
    parts = [
        f"{label}: {handshape_name(states)}",
        "fingers -> " + ", ".join(f"{f} {s}" for f, s in states.items()),
        palm_orientation(lm, side),
        pointing_direction(lm),
        "at " + location(lm),
    ]
    parts += contacts(lm)
    return "; ".join(parts)

def hand_signature(hand):
    lm = hand["landmarks"]
    return (hand.get("handedness"),) + tuple(finger_state(lm, f) for f in FINGERS) + (
        palm_orientation(lm, hand.get("handedness")),
    )

# ---------- keyframe selection ----------

def select_important(raw, max_frames=4):
    """
    Pick the most informative keyframes:
      - always the first and last (start/end posture)
      - frames where the handshape/orientation signature changes
      - manually curated frames (manual_frame_indices) are preferred
    Returns list of (frame_index, keyframe).
    """
    kfs = raw.get("keyframes") or []
    idxs = raw.get("frame_indices") or list(range(len(kfs)))
    manual = set(raw.get("manual_frame_indices") or [])
    frames = [(i, k) for i, k in zip(idxs, kfs) if k.get("hands")]
    if len(frames) <= max_frames:
        return frames
    picked, last_sig = [], None
    for i, k in frames:
        sig = tuple(hand_signature(h) for h in k["hands"])
        if sig != last_sig or i in manual:
            picked.append((i, k))
        last_sig = sig
    if frames[-1] not in picked:
        picked.append(frames[-1])
    if len(picked) > max_frames:  # keep first, last and evenly spaced middles
        step = (len(picked) - 1) / (max_frames - 1)
        picked = [picked[round(n * step)] for n in range(max_frames)]
    return picked

def _video_roi_motion(video_path: str | None, frames: list, raw: dict | None = None) -> str | None:
    """
    Analyze consecutive video frames inside the active signing window around the
    hand's bounding box to detect subtle/repetitive hand movements (double taps,
    oscillations, forward/backward pulses) that happen between sparse keyframes.
    """
    if not video_path or not os.path.exists(video_path):
        return None
    try:
        xs, ys = [], []
        for _, kf in frames:
            for hand in kf.get("hands") or []:
                for p in hand.get("landmarks") or []:
                    xs.append(p["x"])
                    ys.append(p["y"])
        if xs and ys:
            cx = int((sum(xs) / len(xs)) * 800)
            cy = int((sum(ys) / len(ys)) * 600)
            rw, rh = 180, 140
            x0 = max(0, min(800 - rw, cx - rw // 2))
            y0 = max(0, min(600 - rh, cy - rh // 2))
            vf = f"crop={rw}:{rh}:{x0}:{y0},format=gray"
        else:
            rw, rh = 160, 120
            vf = f"scale={rw}:{rh},format=gray"

        raw_bytes = subprocess.check_output(
            ["ffmpeg", "-v", "error", "-i", video_path, "-vf", vf, "-f", "rawvideo", "-"],
            timeout=6.0,
        )
        n = len(raw_bytes) // (rw * rh)
        if n < 10:
            return None
        vframes = [raw_bytes[i * rw * rh : (i + 1) * rw * rh] for i in range(n)]

        f_idxs = [int(i) for i, _ in frames] if frames else ((raw or {}).get("frame_indices") or [])
        if len(f_idxs) == 1:
            # Explicit single-keyframe static sign (e.g. alphabet letters)
            return None
        f_start = max(1, f_idxs[0]) if f_idxs else int(n * 0.25)
        f_end = min(n - 2, f_idxs[-1]) if len(f_idxs) >= 2 else min(n - 4, f_start + 25)
        if f_end <= f_start + 2:
            f_end = min(n - 2, f_start + 20)

        mads = []
        for f in range(f_start, f_end + 1):
            diff = sum(abs(a - b) for a, b in zip(vframes[f], vframes[f - 1])) / (rw * rh)
            mads.append((f, diff))

        peaks = []
        for idx in range(1, len(mads) - 1):
            f, val = mads[idx]
            if val > 2.2 and val >= mads[idx - 1][1] and val >= mads[idx + 1][1]:
                if not peaks or f - peaks[-1][0] >= 3:
                    peaks.append((f, round(val, 1)))

        if len(peaks) >= 2:
            return (
                f"video motion analysis between frame {f_start} and {f_end} detects "
                f"{len(peaks)} distinct motion pulses/repetitive movements of the dominant hand "
                f"(e.g. repeated tap, oscillation, or forward-back motion at the placement point)"
            )
        if len(peaks) == 1:
            return (
                f"video motion analysis between frame {f_start} and {f_end} detects "
                f"a clear single motion stroke/tap of the dominant hand"
            )
    except Exception:
        pass
    return None


def movement_summary(frames, video_path: str | None = None, raw: dict | None = None):
    if len(frames) < 2:
        return "Static sign (single held posture)."

    moves = []
    # 1. Step-by-step trajectory across all consecutive keyframes (wrist + knuckle/fingertip centroids)
    key_pts = [0, 4, 5, 8, 9, 12, 17]
    step_dirs = []
    total_path_xy = 0.0
    for (i1, k1), (i2, k2) in zip(frames, frames[1:]):
        lm1 = k1["hands"][0]["landmarks"]
        lm2 = k2["hands"][0]["landmarks"]
        dx = sum(lm2[p]["x"] - lm1[p]["x"] for p in key_pts) / len(key_pts)
        dy = sum(lm2[p]["y"] - lm1[p]["y"] for p in key_pts) / len(key_pts)
        step_dist = math.hypot(dx, dy)
        total_path_xy += step_dist
        if abs(dx) > 0.025 or abs(dy) > 0.025:
            parts = []
            if abs(dy) > 0.025:
                parts.append("down" if dy > 0 else "up")
            if abs(dx) > 0.025:
                parts.append("sideways")
            step_dirs.append("+".join(parts))

    a, b = frames[0][1]["hands"][0]["landmarks"][0], frames[-1][1]["hands"][0]["landmarks"][0]
    net_dx, net_dy = b["x"] - a["x"], b["y"] - a["y"]
    if abs(net_dx) > 0.06:
        moves.append("moves sideways")
    if abs(net_dy) > 0.06:
        moves.append("moves " + ("downward" if net_dy > 0 else "upward"))
    elif step_dirs:
        moves.append("step movement: " + " then ".join(dict.fromkeys(step_dirs)))

    # 2. Palm orientation / wrist rotation changes across keyframes
    orients = [
        palm_orientation(k["hands"][0]["landmarks"], k["hands"][0].get("handedness") or "Right")
        for _, k in frames
    ]
    unique_orients = list(dict.fromkeys(orients))
    if len(unique_orients) > 1:
        moves.append("wrist/palm rotates (" + " -> ".join(unique_orients) + ")")

    # 3. Handshape transitions across keyframes
    shapes = [
        handshape_name({f: finger_state(k["hands"][0]["landmarks"], f) for f in FINGERS})
        for _, k in frames
    ]
    unique_shapes = list(dict.fromkeys(shapes))
    if len(unique_shapes) > 1:
        moves.append("handshape changes: " + " -> ".join(unique_shapes))

    # 4. Video ROI frame-by-frame motion between keyframes (detects taps/oscillations when keyframes look similar)
    vid_motion = _video_roi_motion(video_path, frames, raw=raw)
    if vid_motion:
        moves.append(vid_motion)

    return ("Dominant hand " + "; ".join(moves) + ".") if moves else "Little hand travel; posture mostly held."

def describe_sign(target, video_path: str | None = None):
    """target = JSON from /api/v1/game/target/{lessonTitle}. Returns text block."""
    raw = target.get("raw") or {}
    title = target.get("lessonTitle") or raw.get("lesson_title")
    default_side = target.get("handedness") or "Right"
    for k in raw.get("keyframes") or []:
        for h in k.get("hands") or []:
            if not h.get("handedness"):
                h["handedness"] = default_side
    frames = select_important(raw)
    fps = raw.get("fps") or 30
    lines = [f"HOW TO SIGN '{title}':"]
    if not frames:
        lines.append("- No keyframe data available; watch the reference video.")
    else:
        hands_used = {h.get("handedness") for _, k in frames for h in k["hands"]}
        is_two = len(hands_used) > 1 or any(len(k["hands"]) > 1 for _, k in frames)
        lines.append(f"- Hands used: {'two-handed sign (dominant + non-dominant hand)' if is_two else 'one-handed sign (dominant hand)'}")
        for n, (i, k) in enumerate(frames, 1):
            t = f"{i / fps:.1f}s" if fps else f"frame {i}"
            for h_idx, h in enumerate(k["hands"]):
                lbl = "Dominant hand" if h_idx == 0 else "Non-dominant hand"
                lines.append(f"- Key posture {n} (at {t}): {describe_hand(h, label=lbl)}")
        lines.append(f"- Movement: {movement_summary(frames, video_path=video_path, raw=raw)}")
    if raw.get("duration"):
        lines.append(f"- Reference video duration: {raw['duration']}s")
    if target.get("videoUrl"):
        lines.append(f"- Reference video: {target['videoUrl']}")
    return "\n".join(lines)
