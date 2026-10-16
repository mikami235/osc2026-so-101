"""CLI for Japanese voice-to-skill routing in dry-run mode."""

import argparse
import subprocess
import sys
import tempfile
from typing import Any

from .audio import record_wav, validate_wav
from .mcp_client import call_skill
from .mock_client import MockAssistant
from .openai_client import OpenAIAdapter
from .robot_executor import RobotRolloutSettings, execute_skill
from .router import RouteResult, route_text


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route Japanese commands to SO-101 skills")
    inputs = parser.add_argument_group("Input")
    input_mode = inputs.add_mutually_exclusive_group(required=True)
    input_mode.add_argument("--text", help="Japanese text input")
    input_mode.add_argument("--audio", help="Path to a WAV file")
    input_mode.add_argument("--mic", action="store_true", help="Record from the default USB microphone")
    inputs.add_argument("--mock", action="store_true", help="Use an API-free mock assistant (text input only)")

    microphone = parser.add_argument_group("Microphone and replies")
    microphone.add_argument(
        "--record-duration",
        "--duration",
        dest="duration",
        type=int,
        default=5,
        help="Recording time in seconds (1-30; --duration is an alias)",
    )
    microphone.add_argument(
        "--microphone-device",
        "--device",
        dest="device",
        help="ALSA capture device (--device is an alias)",
    )
    microphone.add_argument("--loop", action="store_true", help="Keep one microphone session for repeated commands")
    microphone.add_argument("--no-speech", action="store_true", help="Print replies without speaking them")

    robot = parser.add_argument_group("Robot execution")
    robot.add_argument("--enable-robot", action="store_true", help="Enable confirmed LeRobot rollouts from microphone actions")
    robot.add_argument(
        "--rollout-duration",
        type=int,
        default=5,
        help="Maximum time per rollout in seconds (1-30; default: 5)",
    )
    robot.add_argument(
        "--confirmation-mode",
        choices=("required", "none"),
        default="required",
        help="Require typing EXECUTE before each rollout, or run immediately after skill selection",
    )

    hardware = parser.add_argument_group("Robot, cameras, and inference")
    hardware.add_argument("--robot-type", default="so101_follower", help="LeRobot robot type")
    hardware.add_argument("--robot-id", default="so101_follower", help="Calibration ID")
    hardware.add_argument(
        "--robot-port",
        default="/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A7A017797-if00",
        help="Follower serial device",
    )
    hardware.add_argument("--side-camera", default="/dev/video0", help="Device mapped to policy camera key 'side'")
    hardware.add_argument("--top-camera", default="/dev/video2", help="Device mapped to policy camera key 'top'")
    hardware.add_argument("--camera-width", type=int, default=640, help="Camera frame width")
    hardware.add_argument("--camera-height", type=int, default=480, help="Camera frame height")
    hardware.add_argument("--camera-fps", type=int, default=30, help="Camera capture FPS")
    hardware.add_argument("--rollout-fps", type=float, default=20, help="LeRobot control-loop target FPS")
    hardware.add_argument(
        "--policy-device",
        choices=("cpu", "cuda", "mps"),
        default="cpu",
        help="Inference device for policy and processors",
    )
    return parser.parse_args()


def _get_text(args: argparse.Namespace, assistant: OpenAIAdapter) -> str:
    if args.text is not None:
        return args.text
    if args.audio:
        return assistant.transcribe(validate_wav(args.audio))
    with tempfile.TemporaryDirectory(prefix="lerobot-voice-") as temp_dir:
        wav_path = record_wav(f"{temp_dir}/input.wav", duration_s=args.duration, device=args.device)
        return assistant.transcribe(wav_path)


def _speak_with_assistant(text: str, assistant: OpenAIAdapter) -> None:
    with tempfile.TemporaryDirectory(prefix="lerobot-voice-tts-") as temp_dir:
        wav_path = f"{temp_dir}/reply.wav"
        assistant.synthesize_speech(text, wav_path)
        subprocess.run(["aplay", "-q", wav_path], check=True)


def _print_result(
    result: RouteResult,
    speak: bool = True,
    assistant: Any = None,
    show_recognized: bool = True,
    mode: str | None = None,
) -> None:
    if result.conversation is not None:
        print(result.conversation)
        if speak and assistant is not None and hasattr(assistant, "synthesize_speech"):
            _speak_with_assistant(result.conversation, assistant)
        return
    if show_recognized:
        print(f"Recognized: {result.recognized}")
    print(f"Selected Skill: {result.skill}")
    print(f"Mode: {mode or result.mode}")
    print(f"Result: {result.result}")


def _create_rollout_settings(args: argparse.Namespace) -> RobotRolloutSettings:
    return RobotRolloutSettings(
        robot_type=args.robot_type,
        robot_id=args.robot_id,
        robot_port=args.robot_port,
        side_camera=args.side_camera,
        top_camera=args.top_camera,
        camera_width=args.camera_width,
        camera_height=args.camera_height,
        camera_fps=args.camera_fps,
        rollout_fps=args.rollout_fps,
        policy_device=args.policy_device,
    )


def _process_utterance(args: argparse.Namespace, assistant: Any) -> None:
    text = _get_text(args, assistant)
    is_audio_input = args.audio is not None or args.mic
    if is_audio_input:
        print(f"Recognized: {text}")

    if args.enable_robot:
        def dispatch(skill: str, target: str) -> str:
            print(f"Selected Skill: {skill} ({target})")
            return execute_skill(
                skill,
                target,
                duration_s=args.rollout_duration,
                require_confirmation=args.confirmation_mode == "required",
                settings=_create_rollout_settings(args),
            )

    elif args.mock:
        def dispatch(skill: str, target: str) -> str:
            return "MOCK_SUCCESS"

    else:
        dispatch = call_skill

    result = route_text(text, assistant, dispatch)
    _print_result(
        result,
        speak=not args.no_speech,
        assistant=assistant,
        show_recognized=not is_audio_input,
        mode=(
            f"ROBOT ({'CONFIRMED' if args.confirmation_mode == 'required' else 'NO CONFIRMATION'})"
            if args.enable_robot
            else None
        ),
    )


def main() -> int:
    args = _parse_args()
    if args.mic and not 1 <= args.duration <= 30:
        print("Error: recording duration must be between 1 and 30 seconds", file=sys.stderr)
        return 2
    if args.mock and (args.audio or args.mic):
        print("Error: --mock supports --text input only", file=sys.stderr)
        return 2
    if args.loop and not args.mic:
        print("Error: --loop requires --mic", file=sys.stderr)
        return 2
    if args.enable_robot and (not args.mic or args.mock):
        print("Error: --enable-robot requires microphone input and cannot be combined with --mock", file=sys.stderr)
        return 2
    if args.confirmation_mode == "none" and not args.enable_robot:
        print("Error: --confirmation-mode=none requires --enable-robot", file=sys.stderr)
        return 2
    if not 1 <= args.rollout_duration <= 30:
        print("Error: rollout duration must be between 1 and 30 seconds", file=sys.stderr)
        return 2
    if min(args.camera_width, args.camera_height, args.camera_fps) <= 0 or args.rollout_fps <= 0:
        print("Error: camera dimensions and camera/rollout FPS must be positive", file=sys.stderr)
        return 2
    try:
        assistant = MockAssistant() if args.mock else OpenAIAdapter()
        if args.enable_robot and args.confirmation_mode == "none":
            print("WARNING: robot action confirmation is disabled; matched actions run immediately.", file=sys.stderr)
        while True:
            _process_utterance(args, assistant)
            if not args.loop:
                break
            next_utterance = input("\nEnterで次の録音、qで終了: ").strip().lower()
            if next_utterance == "q":
                break
    except KeyboardInterrupt:
        print("\nSpeech interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
