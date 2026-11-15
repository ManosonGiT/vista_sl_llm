"""
Phase 2 of the pipeline: Multimodal VLM analysis of extracted keyframe images
(+ MediaPipe hand landmark geometry when available) for all 109 lessons.

For each lesson, the VLM (`google/gemma-4-26B-A4B-it` on :9001) inspects the
actual extracted keyframe JPEG images (`keyframes/frames/lesson_XXX/frame_YYYYY.jpg`)
alongside any MediaPipe hand measurements and extracts the important factors:
  - Handshape & finger configuration
  - Hand placement relative to body/face (mouth, chin, forehead, chest, etc.)
  - Mouthing, lip movement, facial expression & head posture
  - Hand movement trajectory across keyframes
  - Per-keyframe breakdown (`per_keyframe`)
  - Key features to get right & common learner mistakes

Results are saved to `keyframes/enriched.json` AND synced to the database (`db_store.py`).

Usage:
  venv/bin/python -m keyframes.enrich_with_llm [--limit N] [--force] [--vlm-only]
"""
import os
import sys
import json
import base64
import asyncio
import argparse
import re

import httpx
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keyframes.sign_describer import describe_sign  # noqa: E402
from keyframes.db_store import sync_to_db  # noqa: E402

load_dotenv()
LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:9001").rstrip("/")
LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "google/gemma-4-E4B-it")


def detect_llm_model(url: str = LLM_URL, fallback: str = LLM_MODEL) -> str:
    try:
        r = httpx.get(f"{url}/v1/models", timeout=3.0)
        if r.status_code == 200:
            models = r.json().get("data") or []
            if models and models[0].get("id"):
                return models[0]["id"]
    except Exception:
        pass
    return fallback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE_FILE = os.path.join(HERE, "cache.json")
ENRICHED_FILE = os.path.join(HERE, "enriched.json")

SYSTEM = """You are an expert Greek Sign Language (GSL / Ελληνική Νοηματική Γλώσσα) teacher analyzing keyframe images from an official VISTA-SL teacher video.
You receive:
1. The actual keyframe images from the teacher video (in chronological order). The teacher in the video is ALWAYS performing the sign correctly.
2. Auxiliary MediaPipe hand-landmark measurements (when available) to help confirm which fingers are extended or curled.

CRITICAL RULES:
- ALWAYS refer to the signing hand as the "dominant hand" (in Greek: "κυρίαρχο χέρι") — and "non-dominant hand" ("μη κυρίαρχο χέρι") if two-handed. NEVER say "right hand", "left hand", "right temple", or "right/left side of frame", so that learners are never confused by camera mirroring. Instead say "your dominant hand", "near your temple/cheek on the dominant side", etc.
- The KEYFRAME IMAGES are your primary source of truth for WHERE the dominant hand is placed on or near the body/face (e.g., touching or near the cheek, temple, forehead, mouth, chin, jaw, ear, chest, or in front of the torso). Never contradict what is visible in the image.
- Pay close attention to the `Movement:` line in the Automatic geometric & video motion analysis! Even when the static keyframe images show the hand in a similar spot (such as at the chin or cheek), if the video motion analysis reports repetitive motion pulses / taps / oscillations or wrist rotation, you MUST describe that hand movement (e.g., tapping twice / forward-and-back / small circular or oscillating motion at the placement point) in `movement`, `movement_el`, `key_features`, `key_features_el`, `learner_instructions`, and `learner_instructions_el`. Never say the hand is completely motionless if video motion pulses are detected!
- Look closely at the teacher's mouth and face in each keyframe: in Greek Sign Language, the signer accompanies signs with silent mouthing (προφορική άρθρωση) of the Greek word and specific facial/eyebrow expressions.
- Provide ALL descriptions in BOTH English and Greek (`_el` fields).
- In all `_el` fields, write ONLY natural modern Greek using Greek script (no foreign scripts or non-Greek words). Use standard Greek terminology:
  * dominant hand = κυρίαρχο χέρι | closed fist = κλειστή γροθιά | open palm = ανοιχτή παλάμη
  * thumb = αντίχειρας | index = δείκτης | middle = μέσος | ring = παράμεσος | pinky = μικρό δάχτυλο
  * extended = τεντωμένος | bent/curled = λυγισμένος | temple = κρόταφος | cheek = μάγουλο | chin = πηγούνι | chest = στήθος
  * facial expression = έκφραση προσώπου | eyebrows = φρύδια | mouthing = προφορική άρθρωση
  * repeated tap / movement = επαναλαμβανόμενη επαφή / κίνηση | forward-and-back = μπρος-πίσω
- Keep each string concise (1-2 sentences max) so the JSON stays compact and valid.

Reply with ONLY valid JSON matching this schema:
{
 "hands": "one-handed | two-handed",
 "hands_el": "με ένα χέρι (κυρίαρχο χέρι) | με δύο χέρια",
 "handshape": "English description of the handshape(s) using 'dominant hand'",
 "handshape_el": "Περιγραφή του σχήματος χεριού στα Ελληνικά (χρησιμοποιώντας 'κυρίαρχο χέρι')",
 "palm_orientation": "English direction the palm faces (e.g., towards viewer, towards signer, sideways towards cheek)",
 "palm_orientation_el": "Προσανατολισμός της παλάμης στα Ελληνικά",
 "location": "English exact placement relative to face/body using 'dominant side' (e.g., beside the cheek/temple, touching chin, in front of chest)",
 "location_el": "Ακριβής τοποθέτηση σε σχέση με το πρόσωπο/σώμα στα Ελληνικά",
 "mouth_and_facial_expression": "English mouthing of the Greek word (lip/mouth shape across frames) and facial/eyebrow expression",
 "mouth_and_facial_expression_el": "Προφορική άρθρωση (mouthing) της λέξης και έκφραση προσώπου/φρυδιών στα Ελληνικά",
 "movement": "English description of how the dominant hand and fingers move (including any taps, oscillations, or wrist rotations)",
 "movement_el": "Περιγραφή της κίνησης του κυρίαρχου χεριού/δαχτύλων (συμπεριλαμβανομένων επαναλαμβανόμενων κινήσεων/επαφών ή περιστροφής καρπού) στα Ελληνικά",
 "per_keyframe": [
   {
     "frame_index": 0,
     "timestamp_s": 0.0,
     "handshape": "English handshape in this frame (dominant hand)",
     "handshape_el": "Σχήμα κυρίαρχου χεριού σε αυτό το καρέ",
     "hand_placement": "English placement relative to face/body in this frame",
     "hand_placement_el": "Τοποθέτηση σε σχέση με το πρόσωπο/σώμα σε αυτό το καρέ",
     "mouth_and_face": "English mouth shape (mouthing) and facial expression in this frame",
     "mouth_and_face_el": "Σχήμα στόματος (άρθρωση) και έκφραση προσώπου σε αυτό το καρέ",
     "posture_notes": "English note on what happens at this stage of the sign",
     "posture_notes_el": "Σημείωση στα Ελληνικά για αυτό το στάδιο του νοήματος"
   }
 ],
 "key_features": ["3-4 most important visual factors in English (using 'dominant hand')"],
 "key_features_el": ["3-4 πιο σημαντικά χαρακτηριστικά στα Ελληνικά (με 'κυρίαρχο χέρι')"],
 "learner_instructions": "2-3 sentence step-by-step instruction in English using 'dominant hand'",
 "learner_instructions_el": "2-3 προτάσεις με οδηγίες βήμα-βήμα στα Ελληνικά χρησιμοποιώντας 'κυρίαρχο χέρι'"
}"""


def _extract_json(text: str):
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else None


def _encode_image_data_url(rel_path: str) -> str | None:
    abs_path = os.path.join(ROOT, rel_path)
    if not os.path.exists(abs_path):
        return None
    with open(abs_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


async def enrich_one(client: httpx.AsyncClient, sem: asyncio.Semaphore, sign: dict, target: dict | None, kf_meta: dict | None):
    video_path = (kf_meta or {}).get("video_path")
    analysis = describe_sign(target, video_path=video_path) if target else (
        f"HOW TO SIGN '{sign['title']}':\n"
        f"- Keyframe indices: {(kf_meta or {}).get('frame_indices', [])}\n"
        f"- Reference video: {(kf_meta or {}).get('video_url', '')}"
    )

    f_indices = (kf_meta or {}).get("frame_indices") or []
    f_images = (kf_meta or {}).get("frame_images") or []
    fps = float((kf_meta or {}).get("fps") or 30.0)

    content_parts = []
    for idx, img_rel in zip(f_indices, f_images):
        data_url = _encode_image_data_url(img_rel)
        if data_url:
            ts = round(int(idx) / fps, 2) if fps else 0.0
            content_parts.append({"type": "text", "text": f"Keyframe at frame {idx} ({ts}s):"})
            content_parts.append({"type": "image_url", "image_url": {"url": data_url}})

    prompt_text = (
        f"Sign: '{sign['title']}' (Lesson ID: {sign['lessonId']}, Module: {sign['moduleTitle']}).\n"
        f"Keyframe frame indices: {f_indices} (fps={fps}).\n"
        f"Automatic geometric analysis:\n{analysis}\n\n"
        "Analyze the keyframe image(s) and geometric data and return ONLY the JSON object."
    )
    content_parts.append({"type": "text", "text": prompt_text})

    async with sem:
        parsed = None
        content = ""
        for attempt in range(2):
            r = await client.post(
                f"{LLM_URL}/v1/chat/completions",
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": content_parts if len(content_parts) > 1 else prompt_text},
                    ],
                    "temperature": 0.1 if attempt == 0 else 0.3,
                    "max_tokens": 2500,
                },
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            try:
                parsed = _extract_json(content)
                if parsed:
                    break
            except json.JSONDecodeError:
                parsed = None
    return {
        "analysis": analysis,
        "frame_indices": f_indices,
        "frame_images": f_images,
        "vlm_used_images": len(content_parts) > 1,
        "llm": parsed,
        "llm_raw": None if parsed else content,
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="Max number of signs to process")
    ap.add_argument("--force", action="store_true", help="Re-run VLM on all lessons even if cached")
    ap.add_argument("--upgrade-vlm", action="store_true", help="Re-run lessons that have not been analyzed with keyframe images yet")
    a = ap.parse_args()

    data = json.load(open(CACHE_FILE, encoding="utf-8"))
    done = {} if a.force or not os.path.exists(ENRICHED_FILE) else json.load(open(ENRICHED_FILE, encoding="utf-8"))
    kf_meta_all = data.get("keyframes_meta") or {}

    def needs_enrichment(s):
        title = s["title"]
        if title not in done or not done[title].get("llm"):
            return True
        has_imgs = bool((kf_meta_all.get(str(s["lessonId"])) or {}).get("frame_images"))
        if a.upgrade_vlm and ((has_imgs and not done[title].get("vlm_used_images")) or not done[title]["llm"].get("learner_instructions_el")):
            return True
        return False

    todo = [s for s in data["signs"] if needs_enrichment(s)]
    if a.limit:
        todo = todo[:a.limit]

    global LLM_MODEL
    LLM_MODEL = detect_llm_model()
    print(f"🤖 Asking VLM ({LLM_MODEL} at {LLM_URL}) to analyze keyframe images for {len(todo)} lessons...")

    sem = asyncio.Semaphore(4)
    lock = asyncio.Lock()
    completed = 0
    async with httpx.AsyncClient(timeout=180.0) as client:
        async def run(s):
            nonlocal completed
            lid = str(s["lessonId"])
            try:
                res = await enrich_one(
                    client, sem, s,
                    data["targets"].get(s["title"]),
                    kf_meta_all.get(lid),
                )
                async with lock:
                    done[s["title"]] = res
                    completed += 1
                    print(f"  ✅ [{s['lessonId']:03d}] {s['title']} ({completed}/{len(todo)}, frames={res['frame_indices']})", flush=True)
                    if completed % 5 == 0:
                        json.dump(done, open(ENRICHED_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                        sync_to_db(data, done)
            except Exception as e:
                print(f"  ❌ [{s['lessonId']:03d}] {s['title']}: {e}", flush=True)

        if todo:
            await asyncio.gather(*(run(s) for s in todo))

    json.dump(done, open(ENRICHED_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"💾 Saved {len(done)} enriched signs -> {ENRICHED_FILE}")

    n_db = sync_to_db(data, done)
    print(f"🗄️  Synced {n_db} lessons & keyframes to SQLite database")


if __name__ == "__main__":
    asyncio.run(main())
