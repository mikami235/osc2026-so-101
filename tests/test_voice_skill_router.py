import json
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from examples.so101.voice_skill_router import cli, mcp_client, robot_executor
from examples.so101.voice_skill_router.audio import record_wav, validate_wav
from examples.so101.voice_skill_router.mock_client import MockAssistant
from examples.so101.voice_skill_router.router import route_text


class FakeAssistant:
    def __init__(self, intent=None, reply="通常の返答", error=None):
        self.intent = intent
        self.reply_text = reply
        self.error = error
        self.classified = []
        self.replied = []
        self.synthesized = []

    def classify_action(self, instruction):
        self.classified.append(instruction)
        if self.error:
            raise self.error
        return self.intent

    def reply(self, message):
        self.replied.append(message)
        if self.error:
            raise self.error
        return self.reply_text

    def synthesize_speech(self, text, wav_path):
        self.synthesized.append(text)
        Path(wav_path).write_bytes(b"wav")


@pytest.mark.parametrize(
    ("text", "intent", "expected_skill", "expected_target"),
    [
        (
            "アクション。右のペン立てに入れて",
            {"skill": "place_pen_right", "target": "right"},
            "place_pen_right",
            "right",
        ),
        (
            "アクション。左に置いて",
            {"skill": "place_pen_left", "target": "left"},
            "place_pen_left",
            "left",
        ),
    ],
)
def test_action_selects_matching_allowlisted_skill(text, intent, expected_skill, expected_target):
    assistant = FakeAssistant(intent=intent)
    calls = []

    result = route_text(text, assistant, lambda skill, target: calls.append((skill, target)) or "MOCK_SUCCESS")

    assert result.skill == expected_skill
    assert result.result == "MOCK_SUCCESS"
    assert calls == [(expected_skill, expected_target)]


def test_non_action_phrase_uses_conversation_without_dispatch():
    assistant = FakeAssistant(intent={"skill": "place_pen_right", "target": "right"})
    calls = []

    result = route_text("右に置く方法を教えて", assistant, lambda *args: calls.append(args))

    assert result.conversation == "通常の返答"
    assert assistant.replied == ["右に置く方法を教えて"]
    assert assistant.classified == []
    assert calls == []


def test_mock_cli_without_api_key_routes_only_prefixed_text(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["voice-skill-router", "--text", "右に置く方法を教えて", "--mock", "--no-speech"])

    assert cli.main() == 0
    assert "[MOCK conversation] 右に置く方法を教えて" in capsys.readouterr().out

    monkeypatch.setattr("sys.argv", ["voice-skill-router", "--text", "アクション。右に置いて", "--mock", "--no-speech"])
    assert cli.main() == 0
    output = capsys.readouterr().out
    assert "Selected Skill: place_pen_right" in output
    assert "Result: MOCK_SUCCESS" in output


def test_cli_speaks_conversation_but_not_action(monkeypatch, capsys):
    assistant = FakeAssistant(intent={"skill": "place_pen_right", "target": "right"})
    playback = []
    monkeypatch.setattr(cli, "OpenAIAdapter", lambda: assistant)
    monkeypatch.setattr(cli.subprocess, "run", lambda command, **kwargs: playback.append(command))
    monkeypatch.setattr(cli, "call_skill", lambda skill, target: "MOCK_SUCCESS")
    monkeypatch.setattr("sys.argv", ["voice-skill-router", "--text", "右に置く方法を教えて"])

    assert cli.main() == 0
    capsys.readouterr()
    assert assistant.synthesized == ["通常の返答"]
    assert len(playback) == 1

    monkeypatch.setattr("sys.argv", ["voice-skill-router", "--text", "アクション。右に置いて"])
    assert cli.main() == 0
    capsys.readouterr()
    assert assistant.synthesized == ["通常の返答"]
    assert len(playback) == 1


def test_mic_cli_displays_transcription_before_conversation(monkeypatch, capsys):
    assistant = FakeAssistant(intent={"skill": "place_pen_right", "target": "right"})
    monkeypatch.setattr(cli, "OpenAIAdapter", lambda: assistant)
    monkeypatch.setattr(cli, "_get_text", lambda args, adapter: "今日はいい天気ですね")
    monkeypatch.setattr(cli, "call_skill", lambda skill, target: "MOCK_SUCCESS")
    monkeypatch.setattr("sys.argv", ["voice-skill-router", "--mic", "--duration", "5", "--no-speech"])

    assert cli.main() == 0

    output = capsys.readouterr().out
    assert "Recognized: 今日はいい天気ですね" in output
    assert "通常の返答" in output

    monkeypatch.setattr(cli, "_get_text", lambda args, adapter: "アクション。右に入れて")
    assert cli.main() == 0
    output = capsys.readouterr().out
    assert output.count("Recognized:") == 1
    assert "Recognized: アクション。右に入れて" in output
    assert "Selected Skill: place_pen_right" in output


def test_microphone_loop_reuses_one_cli_session(monkeypatch, capsys):
    assistant = FakeAssistant(intent={"skill": "place_pen_right", "target": "right"})
    utterances = iter(["こんにちは", "アクション。右に入れて"])
    monkeypatch.setattr(cli, "OpenAIAdapter", lambda: assistant)
    monkeypatch.setattr(cli, "_get_text", lambda args, adapter: next(utterances))
    monkeypatch.setattr(cli, "call_skill", lambda skill, target: "MOCK_SUCCESS")
    input_values = iter(["", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(input_values))
    monkeypatch.setattr("sys.argv", ["voice-skill-router", "--mic", "--loop", "--no-speech"])

    assert cli.main() == 0

    output = capsys.readouterr().out
    assert output.count("Recognized:") == 2
    assert "Selected Skill: place_pen_right" in output
    assert "Result: MOCK_SUCCESS" in output


def test_robot_executor_uses_fixed_left_model_and_cpu(monkeypatch):
    calls = []
    monkeypatch.setattr(robot_executor.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))

    result = robot_executor.execute_skill("place_pen_left", "left", confirm=lambda prompt: True)

    assert result == "LEROBOT_ROLLOUT_COMPLETED"
    command, options = calls[0]
    model_path = robot_executor.REPO_ROOT / "models/act_so101_pen_center_left_5ep_v1"
    assert f"--policy.path={model_path}" in command
    assert "--device=cpu" in command
    assert "--policy.device=cpu" in command
    assert "--duration=5" in command
    assert "--return_to_initial_position=false" in command
    assert options == {"cwd": robot_executor.REPO_ROOT, "check": True}


def test_robot_executor_serializes_readable_rollout_settings():
    settings = robot_executor.RobotRolloutSettings(
        robot_port="/dev/ttyACM7",
        side_camera="/dev/video4",
        top_camera="/dev/video6",
        camera_width=640,
        camera_height=480,
        camera_fps=25,
        rollout_fps=12.5,
        policy_device="cpu",
    )

    command = robot_executor.build_rollout_command("place_pen_right", duration_s=8, settings=settings)

    camera_argument = next(argument for argument in command if argument.startswith("--robot.cameras="))
    cameras = json.loads(camera_argument.split("=", 1)[1])
    assert cameras["side"]["index_or_path"] == "/dev/video4"
    assert cameras["top"]["index_or_path"] == "/dev/video6"
    assert cameras["side"]["fps"] == 25
    assert "--robot.port=/dev/ttyACM7" in command
    assert "--fps=12.5" in command
    assert "--duration=8" in command


def test_robot_executor_requires_confirmation_and_matching_target(monkeypatch):
    calls = []
    monkeypatch.setattr(robot_executor.subprocess, "run", lambda *args, **kwargs: calls.append(args))

    assert robot_executor.execute_skill("place_pen_right", "right", confirm=lambda prompt: False) == "CANCELLED"
    with pytest.raises(ValueError, match="not allowlisted"):
        robot_executor.execute_skill("place_pen_right", "left", confirm=lambda prompt: True)
    assert calls == []


def test_robot_executor_can_skip_confirmation_when_explicitly_requested(monkeypatch):
    calls = []
    monkeypatch.setattr(robot_executor.subprocess, "run", lambda command, **kwargs: calls.append(command))
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("confirmation prompt should be skipped"))

    result = robot_executor.execute_skill(
        "place_pen_right",
        "right",
        require_confirmation=False,
    )

    assert result == "LEROBOT_ROLLOUT_COMPLETED"
    assert len(calls) == 1


def test_cli_no_confirmation_mode_needs_robot_opt_in(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        ["voice-skill-router", "--text", "アクション。右に入れて", "--confirmation-mode", "none"],
    )

    assert cli.main() == 2
    assert "requires --enable-robot" in capsys.readouterr().err


def test_cli_no_confirmation_mode_dispatches_without_prompt(monkeypatch, capsys):
    assistant = FakeAssistant(intent={"skill": "place_pen_right", "target": "right"})
    calls = []
    monkeypatch.setattr(cli, "OpenAIAdapter", lambda: assistant)
    monkeypatch.setattr(cli, "_get_text", lambda args, adapter: "アクション。右に入れて")
    monkeypatch.setattr(
        cli,
        "execute_skill",
        lambda skill, target, duration_s, require_confirmation, settings: calls.append(
            (skill, target, duration_s, require_confirmation, settings)
        )
        or "LEROBOT_ROLLOUT_COMPLETED",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "voice-skill-router",
            "--mic",
            "--enable-robot",
            "--confirmation-mode",
            "none",
            "--no-speech",
        ],
    )

    assert cli.main() == 0

    assert len(calls) == 1
    skill, target, duration, confirmation, settings = calls[0]
    assert (skill, target, duration, confirmation) == ("place_pen_right", "right", 5, False)
    assert settings.side_camera == "/dev/video0"
    assert settings.top_camera == "/dev/video2"
    assert "confirmation is disabled" in capsys.readouterr().err


def test_openai_adapter_writes_generated_wav(tmp_path, monkeypatch):
    from examples.so101.voice_skill_router.openai_client import OpenAIAdapter

    class FakeSpeechResponse:
        def stream_to_file(self, path):
            Path(path).write_bytes(b"wav-data")

    calls = []
    adapter = OpenAIAdapter.__new__(OpenAIAdapter)
    adapter._client = SimpleNamespace(
        audio=SimpleNamespace(
            speech=SimpleNamespace(
                create=lambda **kwargs: calls.append(kwargs) or FakeSpeechResponse()
            )
        )
    )
    wav_path = tmp_path / "reply.wav"

    adapter.synthesize_speech("こんにちは", wav_path)

    assert calls == [
        {
            "model": "gpt-4o-mini-tts",
            "voice": "alloy",
            "input": "こんにちは",
            "response_format": "wav",
        }
    ]
    assert wav_path.read_bytes() == b"wav-data"


def test_mock_assistant_returns_none_for_ambiguous_direction():
    assistant = MockAssistant()

    assert assistant.classify_action("右か左に置いて") == {"skill": "none", "target": None}


@pytest.mark.parametrize("text", ["アクション", "アクション。", "アクション。よくわからない"])
def test_empty_or_unsupported_action_never_dispatches(text):
    assistant = FakeAssistant(intent={"skill": "none", "target": None})
    calls = []

    result = route_text(text, assistant, lambda *args: calls.append(args))

    assert result.skill == "none"
    assert result.result == "NO_ACTION"
    assert calls == []


def test_unregistered_skill_is_rejected_before_dispatch():
    assistant = FakeAssistant(intent={"skill": "execute_shell", "target": "right"})
    calls = []

    with pytest.raises(ValueError, match="allowlisted"):
        route_text("アクション。右に置いて", assistant, lambda *args: calls.append(args))

    assert calls == []


def test_mismatched_target_is_rejected_before_dispatch():
    assistant = FakeAssistant(intent={"skill": "place_pen_right", "target": "left"})
    calls = []

    with pytest.raises(ValueError, match="do not match"):
        route_text("アクション。右に置いて", assistant, lambda *args: calls.append(args))

    assert calls == []


def test_api_failure_never_dispatches():
    assistant = FakeAssistant(error=RuntimeError("API unavailable"))
    calls = []

    with pytest.raises(RuntimeError, match="API unavailable"):
        route_text("アクション。右に置いて", assistant, lambda *args: calls.append(args))

    assert calls == []


@pytest.mark.parametrize(
    ("skill", "target"),
    [("place_pen_right", "right"), ("place_pen_left", "left")],
)
def test_stdio_mcp_server_returns_mock_success(skill, target):
    assert mcp_client.call_skill(skill, target) == "MOCK_SUCCESS"


def test_mcp_server_rejects_unregistered_tool(monkeypatch):
    monkeypatch.setitem(mcp_client.SKILL_TARGETS, "place_pen_center", "center")

    with pytest.raises(RuntimeError, match="not registered"):
        mcp_client.call_skill("place_pen_center", "center")


def test_wav_validation_and_recording_duration(tmp_path, monkeypatch):
    wav_path = tmp_path / "valid.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00")

    assert validate_wav(wav_path) == wav_path
    with pytest.raises(ValueError, match="between 1 and 30"):
        record_wav(tmp_path / "unused.wav", duration_s=0)
    invalid_wav = tmp_path / "invalid.wav"
    invalid_wav.write_bytes(b"not a wave file")
    with pytest.raises(ValueError, match="Not a valid WAV"):
        validate_wav(invalid_wav)
