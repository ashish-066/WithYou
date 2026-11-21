"""Throwaway Sarvam probes (BUILD_PLAN §6). Not part of the app.

Run from the repo root (reads SARVAM_API_KEY from avatar/.env or the environment):

  uv run --with httpx --with python-dotenv python spikes/sarvam_probe.py tts
  uv run --with httpx --with python-dotenv python spikes/sarvam_probe.py stt path/to/clip.wav
  uv run --with httpx --with python-dotenv python spikes/sarvam_probe.py llm

Request shapes mirror livekit-plugins-sarvam 1.8.10 (stt.py / tts.py / llm/client.py).
Responses are printed with the audio/base64 stripped so the real schema is visible.
"""

import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "avatar" / ".env")
load_dotenv(ROOT / "worker" / ".env")
KEY = os.environ.get("SARVAM_API_KEY", "")
OUT = ROOT / "spikes" / "out"
BASE = "https://api.sarvam.ai"


def _headers() -> dict[str, str]:
    if not KEY:
        sys.exit("SARVAM_API_KEY is not set (add it to avatar/.env)")
    return {"api-subscription-key": KEY}


def _show(resp: httpx.Response, elapsed: float) -> dict:
    print(f"HTTP {resp.status_code} in {elapsed:.2f}s")
    try:
        data = resp.json()
    except ValueError:
        print(resp.text[:500])
        return {}
    redacted = {k: (f"<{len(v)} items>" if k == "audios" else v) for k, v in data.items()}
    print(json.dumps(redacted, ensure_ascii=False, indent=2)[:1500])
    return data


def tts(text: str = "നമസ്കാരം, നമുക്ക് ഒരുമിച്ച് പഠിക്കാം. ഇന്ന് എന്താണ് പഠിക്കേണ്ടത്?",
        speaker: str = "shubh") -> None:
    payload = {
        "text": text,
        "target_language_code": "ml-IN",
        "model": "bulbul:v3",
        "speaker": speaker,
        "speech_sample_rate": 22050,
    }
    t = time.perf_counter()
    resp = httpx.post(f"{BASE}/text-to-speech", json=payload, headers=_headers(), timeout=60)
    data = _show(resp, time.perf_counter() - t)
    audios = data.get("audios") or []
    if audios:
        OUT.mkdir(parents=True, exist_ok=True)
        path = OUT / f"p0_bulbul_v3_ml_{speaker}.wav"
        path.write_bytes(base64.b64decode(audios[0]))
        print(f"\nSaved {path}  →  play it:  afplay {path}")


def stt(clip: str, model: str = "saaras:v3") -> None:
    audio = Path(clip).read_bytes()
    files = {"file": (Path(clip).name, audio, "audio/wav")}
    data = {"model": model, "language_code": "ml-IN"}
    t = time.perf_counter()
    resp = httpx.post(f"{BASE}/speech-to-text", files=files, data=data, headers=_headers(), timeout=60)
    _show(resp, time.perf_counter() - t)


def llm(prompt: str = "പ്രകാശസംശ്ലേഷണം എന്താണെന്ന് രണ്ട് വാക്യത്തിൽ ലളിതമായി പറഞ്ഞുതരാമോ?") -> None:
    payload = {
        "model": "sarvam-105b",
        "messages": [
            {"role": "system", "content": "You are a warm study buddy. Reply in Malayalam, briefly."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
    }
    headers = {**_headers(), "Authorization": f"Bearer {KEY}"}
    t = time.perf_counter()
    resp = httpx.post(f"{BASE}/v2/chat/completions", json=payload, headers=headers, timeout=60)
    _show(resp, time.perf_counter() - t)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tts"
    args = sys.argv[2:]
    {"tts": tts, "stt": stt, "llm": llm}[cmd](*args)
