

import asyncio
import tempfile
from pathlib import Path

import edge_tts
from faster_whisper import WhisperModel

_whisper_model = None


def get_whisper_model(model_size: str = "base") -> WhisperModel:
    """Lazy-load so app startup is fast; the model stays cached across calls."""
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _whisper_model


def transcribe_audio(audio_path: str) -> str:
    model = get_whisper_model()
    segments, _info = model.transcribe(audio_path, beam_size=5)
    return " ".join(seg.text.strip() for seg in segments).strip()


async def _generate_tts(text: str, voice: str, out_path: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_path)


def synthesize_speech(text: str, voice: str = "en-US-AriaNeural") -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        out_path = tmp.name
    asyncio.run(_generate_tts(text, voice, out_path))
    data = Path(out_path).read_bytes()
    Path(out_path).unlink(missing_ok=True)
    return data
