# backend/app/tts.py
from gtts import gTTS
from io import BytesIO

def text_to_speech_mp3(text: str, lang: str = "ro") -> bytes:
    """
    Generate MP3 bytes in memory (no temp files -> Windows-safe).
    Requires internet access for gTTS.
    """
    t = (text or "I have nothing to read.").strip()
    tts = gTTS(t, lang=lang)
    buf = BytesIO()
    tts.write_to_fp(buf)
    buf.seek(0)
    return buf.read()
