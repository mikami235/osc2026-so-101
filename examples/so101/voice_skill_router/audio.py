"""Linux ALSA recording helpers for the voice skill router."""

import subprocess
import wave
from pathlib import Path


def validate_wav(path: str | Path) -> Path:
    """Return a validated WAV path suitable for transcription."""
    wav_path = Path(path)
    if not wav_path.is_file():
        raise FileNotFoundError(f"Audio file does not exist: {wav_path}")
    try:
        with wave.open(str(wav_path), "rb") as wav_file:
            if wav_file.getnframes() == 0:
                raise ValueError("Audio file contains no frames")
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"Not a valid WAV file: {wav_path}") from exc
    return wav_path


def record_wav(output_path: str | Path, duration_s: int = 5, device: str | None = None) -> Path:
    """Record mono 16 kHz PCM audio using the system arecord utility."""
    if not 1 <= duration_s <= 30:
        raise ValueError("Recording duration must be between 1 and 30 seconds")

    wav_path = Path(output_path)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    command = ["arecord", "-q", "-f", "S16_LE", "-c", "1", "-r", "16000", "-d", str(duration_s)]
    if device:
        command.extend(["-D", device])
    command.append(str(wav_path))
    subprocess.run(command, check=True, capture_output=True, text=True)
    return validate_wav(wav_path)