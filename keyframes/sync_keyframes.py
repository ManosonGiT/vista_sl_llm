"""
Phase 1: Sync all 109 sign lessons, landmarks, videos, motion keyframe picks, and
extracted keyframe JPEG images locally.

  1. Uses cached or live /api/v1/game/signs (109 lessons) and /api/v1/game/target/{title} (67 landmark targets)
  2. Downloads all 109 teacher videos from https://catsl.eelvex.net/static/vid/teacher-video-{title}.mp4
     into keyframes/videos/lesson_{lessonId:03d}_{title}.mp4
  3. Selects keyframe indices:
       - Uses published manual/reference `frame_indices` when present
       - Otherwise computes frame-to-frame motion locally from the video to pick 3 key postures
         (start, peak/apex, end of sign)
  4. Extracts keyframe JPEGs via ffmpeg into keyframes/frames/lesson_{lessonId:03d}/frame_{idx:05d}.jpg
  5. Saves full metadata to keyframes/cache.json, updates signing_knowledge_base.txt,
     and syncs everything to the SQLite database (keyframes/db_store.py).

Usage:
  venv/bin/python -m keyframes.sync_keyframes              # fetch/reuse cache, download videos, extract frames, sync DB
  venv/bin/python -m keyframes.sync_keyframes --no-upload  # skip AnythingLLM upload
  venv/bin/python -m keyframes.sync_keyframes --cached     # reuse cache.json signs/targets without hitting vistasl login
"""
import os
import sys
import json
import asyncio
import argparse
import subprocess
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keyframes.sign_describer import describe_sign, select_important  # noqa: E402
from keyframes.db_store import sync_to_db  # noqa: E402

load_dotenv()

PLATFORM_URL = os.getenv("PLATFORM_URL", "https://vistasl.eelvex.net").rstrip("/")
VIDEO_CDN_URL = os.getenv("VIDEO_CDN_URL", "https://catsl.eelvex.net").rstrip("/")
PLATFORM_USER = os.getenv("PLATFORM_USER", "admin")
PLATFORM_PASS = os.getenv("PLATFORM_PASS", "")

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(HERE, "cache.json")
VIDEOS_DIR = os.path.join(HERE, "videos")
FRAMES_DIR = os.path.join(HERE, "frames")
KB_FILE = os.path.join(os.path.dirname(HERE), "signing_knowledge_base.txt")
LESSON_URL = PLATFORM_URL + "/lesson/{}"


def probe_video(video_path):
    """Return (fps, duration, total_frames) for a local video using ffprobe."""
    if not video_path or not os.path.exists(video_path):
        return 30.0, 3.5, 105
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate,duration,nb_frames",
            "-of", "json", video_path,
        ], text=True, timeout=5.0)
        st = (json.loads(out).get("streams") or [{}])[0]
        r_fps = st.get("r_frame_rate", "30/1")
        num, den = (r_fps.split("/") + ["1"])[:2]
        fps = float(num) / max(1.0, float(den))
        dur = float(st.get("duration") or 3.5)
        nbf = int(st.get("nb_frames") or round(fps * dur))
        return fps, dur, nbf
    except Exception:
        return 30.0, 3.5, 105


def compute_local_motion_picks(video_path, k=3):
    """
    Decode downscaled 64x36 grayscale frames via ffmpeg and pick `k` representative
    signing keyframes (start of active signing, peak posture, end of active signing),
    avoiding rest frames at the very start/end of the clip.
    """
    if not video_path or not os.path.exists(video_path):
        return [30, 50, 70]
    w, h = 64, 36
    frame_sz = w * h
    try:
        raw_bytes = subprocess.check_output([
            "ffmpeg", "-v", "error", "-i", video_path,
            "-vf", f"scale={w}:{h},format=gray",
            "-f", "rawvideo", "-",
        ], timeout=10.0)
        n_frames = len(raw_bytes) // frame_sz
        if n_frames < 6:
            return [max(0, n_frames // 2)]

        frames = [raw_bytes[i * frame_sz:(i + 1) * frame_sz] for i in range(n_frames)]
        motion = [0.0]
        for i in range(1, n_frames):
            a, b = frames[i - 1], frames[i]
            diff = sum(abs(x - y) for x, y in zip(a, b)) / (frame_sz * 255.0)
            motion.append(diff)

        # Active signing window (ignore first 15% rest/raise and last 15% drop)
        lo = max(1, int(n_frames * 0.18))
        hi = max(lo + 3, int(n_frames * 0.82))
        active = motion[lo:hi]
        max_m = max(active) if active else 0.0
        thresh = max_m * 0.25

        active_idxs = [i for i in range(lo, hi) if motion[i] >= thresh]
        if len(active_idxs) >= 3:
            start_f = active_idxs[0]
            end_f = active_idxs[-1]
            mid_f = (start_f + end_f) // 2
            # If the sign holds a steady posture in the middle, pick that held frame + start/end
            picks = sorted({start_f, mid_f, end_f})
            if len(picks) == k:
                return picks

        return sorted({int(n_frames * 0.30), int(n_frames * 0.50), int(n_frames * 0.70)})
    except Exception:
        return [30, 50, 70]


def choose_frame_indices(target, video_path, max_frames=4):
    """
    Determine the best keyframe indices (0-based frame numbers) for a lesson:
      1. If target.raw has frame_indices / manual_frame_indices, use select_important on them.
      2. Otherwise compute active-signing keyframes directly from the local video.
    """
    raw = (target or {}).get("raw") or {}
    if raw.get("frame_indices"):
        picked = [idx for idx, _ in select_important(raw, max_frames=max_frames)]
        if picked:
            return sorted(set(int(i) for i in picked))

    return compute_local_motion_picks(video_path, k=min(3, max_frames))


def extract_frames_ffmpeg(video_path, lesson_id, frame_indices):
    """
    Extract specific 0-based frame indices from video_path using ffmpeg into
    keyframes/frames/lesson_{lesson_id:03d}/frame_{idx:05d}.jpg.
    Returns list of relative paths (from project root) to extracted JPEGs.
    """
    lesson_dir = os.path.join(FRAMES_DIR, f"lesson_{lesson_id:03d}")
    os.makedirs(lesson_dir, exist_ok=True)
    root_dir = os.path.dirname(HERE)

    out_paths = []
    for idx in frame_indices:
        jpg_path = os.path.join(lesson_dir, f"frame_{idx:05d}.jpg")
        rel_path = os.path.relpath(jpg_path, root_dir)
        if not os.path.exists(jpg_path) or os.path.getsize(jpg_path) == 0:
            select_expr = f"eq(n\\,{idx})"
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", video_path,
                "-vf", f"select={select_expr}",
                "-frames:v", "1",
                "-q:v", "2",
                jpg_path,
            ]
            subprocess.run(cmd, check=False)
            if not os.path.exists(jpg_path) or os.path.getsize(jpg_path) == 0:
                subprocess.run([
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-sseof", "-0.5", "-i", video_path,
                    "-frames:v", "1", "-q:v", "2", jpg_path,
                ], check=False)
        if os.path.exists(jpg_path) and os.path.getsize(jpg_path) > 0:
            out_paths.append(rel_path)

    return out_paths


async def fetch_all(use_cached_signs=False):
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    os.makedirs(FRAMES_DIR, exist_ok=True)
    root_dir = os.path.dirname(HERE)

    existing = {}
    if os.path.exists(CACHE_FILE):
        try:
            existing = json.load(open(CACHE_FILE, encoding="utf-8"))
        except Exception:
            existing = {}

    signs = existing.get("signs") or []
    targets = existing.get("targets") or {}

    if not use_cached_signs or not signs:
        try:
            async with httpx.AsyncClient(base_url=PLATFORM_URL, timeout=15.0, follow_redirects=False) as c:
                r = await c.post("/login", data={"username": PLATFORM_USER, "password": PLATFORM_PASS})
                if r.status_code in (302, 303) and "login" not in r.headers.get("location", ""):
                    print("🔐 Logged in to platform")
                    r_signs = await c.get("/api/v1/game/signs")
                    if r_signs.status_code == 200:
                        signs = r_signs.json()["items"]
                        print(f"📋 {len(signs)} signs fetched from platform")
                    sem_t = asyncio.Semaphore(6)
                    async def fetch_target(item):
                        title = item["title"]
                        if title in targets and targets[title]:
                            return title, targets[title]
                        if not item.get("hasReference"):
                            return title, None
                        async with sem_t:
                            resp = await c.get(f"/api/v1/game/target/{quote(title)}")
                            return title, (resp.json() if resp.status_code == 200 else None)
                    targets = dict(await asyncio.gather(*(fetch_target(i) for i in signs)))
        except Exception as e:
            print(f"ℹ️  Platform live endpoint busy ({e}); using cached signs ({len(signs)} signs) & static CDN.")

    print(f"🎬 Downloading teacher videos for all {len(signs)} lessons from {VIDEO_CDN_URL}...")
    sem_v = asyncio.Semaphore(12)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as cdn_client:
        async def download_video(item):
            lid = item["lessonId"]
            title = item["title"]
            safe_title = title.replace("/", "_")
            vpath = os.path.join(VIDEOS_DIR, f"lesson_{lid:03d}_{safe_title}.mp4")
            if os.path.exists(vpath) and os.path.getsize(vpath) > 1000:
                return lid, os.path.relpath(vpath, root_dir)
            async with sem_v:
                for base in (VIDEO_CDN_URL, PLATFORM_URL):
                    try:
                        resp = await cdn_client.get(f"{base}/static/vid/teacher-video-{quote(title)}.mp4")
                        if resp.status_code == 200 and len(resp.content) > 1000:
                            with open(vpath, "wb") as vf:
                                vf.write(resp.content)
                            return lid, os.path.relpath(vpath, root_dir)
                    except Exception:
                        continue
            return lid, None

        videos = dict(await asyncio.gather(*(download_video(i) for i in signs)))

    print("🖼️  Selecting keyframe indices & extracting keyframe JPEGs with ffmpeg...")
    keyframes_meta = {}
    total_jpgs = 0
    for item in signs:
        lid = item["lessonId"]
        title = item["title"]
        t = targets.get(title)
        vrel = videos.get(lid)
        vabs = os.path.join(root_dir, vrel) if vrel else None

        raw = (t or {}).get("raw") or {}
        p_fps, p_dur, p_tot = probe_video(vabs)
        fps = raw.get("fps") or p_fps
        duration = raw.get("duration") or p_dur
        total_frames = raw.get("total_frames") or p_tot

        f_indices = choose_frame_indices(t, vabs, max_frames=4)
        jpg_rels = extract_frames_ffmpeg(vabs, lid, f_indices) if vabs and os.path.exists(vabs) else []
        total_jpgs += len(jpg_rels)

        keyframes_meta[str(lid)] = {
            "lessonId": lid,
            "title": title,
            "video_path": vrel,
            "video_url": (t or {}).get("videoUrl") or f"{VIDEO_CDN_URL}/static/vid/teacher-video-{quote(title)}.mp4",
            "fps": fps,
            "duration": duration,
            "total_frames": total_frames,
            "frame_indices": f_indices,
            "frame_images": jpg_rels,
            "source": "manual" if raw.get("frame_indices") else "video_motion_auto",
        }

    data = {
        "signs": signs,
        "targets": targets,
        "keyframes_meta": keyframes_meta,
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    ok_t = sum(1 for v in targets.values() if v)
    ok_v = sum(1 for v in videos.values() if v)
    print(f"✅ Synced {len(signs)} lessons: {ok_t} landmark targets, "
          f"{ok_v}/{len(signs)} local videos, {total_jpgs} extracted keyframe JPEGs -> {CACHE_FILE}")
    return data


def build_kb(data):
    n_db = sync_to_db(data)
    print(f"🗄️  Synced {n_db} lessons and keyframes into SQLite database")
    from keyframes.local_rag import build as build_rag_files
    build_rag_files()


async def upload():
    from llm_service import upload_document, update_embeddings
    loc = await upload_document(KB_FILE)
    if not loc:
        raise SystemExit("❌ Upload to AnythingLLM failed")
    print(f"📤 Uploaded: {loc}")
    if await update_embeddings(loc):
        print("🎉 Embedded in workspace — the LLM can now explain how each sign is made.")
    else:
        print("❌ Embedding failed")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--cached", action="store_true")
    a = ap.parse_args()
    data = await fetch_all(use_cached_signs=a.cached)
    build_kb(data)
    if not a.no_upload:
        await upload()


if __name__ == "__main__":
    asyncio.run(main())
