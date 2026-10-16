"""OpenAI API adapter. The SDK is imported only when the example is run."""

import json
import os
from pathlib import Path
from typing import Any

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "skill": {"type": "string", "enum": ["place_pen_right", "place_pen_left", "none"]},
        "target": {"type": ["string", "null"], "enum": ["right", "left", None]},
    },
    "required": ["skill", "target"],
    "additionalProperties": False,
}


class OpenAIAdapter:
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini") -> None:
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the voice extra with: uv sync --extra voice") from exc
        self._client = OpenAI(api_key=resolved_key)
        self._model = model

    def transcribe(self, wav_path: str | Path) -> str:
        with Path(wav_path).open("rb") as audio_file:
            response = self._client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file,
                language="ja",
            )
        text = response.text.strip()
        if not text:
            raise RuntimeError("Audio transcription returned no text")
        return text

    def classify_action(self, instruction: str) -> dict[str, Any]:
        response = self._client.responses.create(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Classify the Japanese request to place a pen. "
                        "Examples: '右のペン立てに入れて' and 'ペンを右側に移して' select "
                        "place_pen_right with target right; '左に置いて' selects place_pen_left "
                        "with target left. Select none for unsupported or ambiguous requests and "
                        "return target null for none."
                    ),
                },
                {"role": "user", "content": instruction},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "skill_intent",
                    "strict": True,
                    "schema": INTENT_SCHEMA,
                }
            },
        )
        try:
            intent = json.loads(response.output_text)
        except (AttributeError, json.JSONDecodeError) as exc:
            raise RuntimeError("OpenAI returned an invalid structured response") from exc
        if not isinstance(intent, dict):
            raise RuntimeError("OpenAI returned an invalid structured response")
        return intent

    def reply(self, message: str) -> str:
        response = self._client.responses.create(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": "You are a concise Japanese voice assistant. Do not call or suggest robot skills.",
                },
                {"role": "user", "content": message},
            ],
        )
        text = response.output_text.strip()
        if not text:
            raise RuntimeError("OpenAI returned an empty reply")
        return text

    def synthesize_speech(self, text: str, wav_path: str | Path) -> None:
        response = self._client.audio.speech.create(
            model=os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
            voice=os.environ.get("OPENAI_TTS_VOICE", "alloy"),
            input=text,
            response_format="wav",
        )
        response.stream_to_file(Path(wav_path))
