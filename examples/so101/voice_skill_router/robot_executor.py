"""Fixed, confirmation-gated LeRobot rollout executor for the SO-101 demo."""

import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ROLLOUT_DURATION_LIMIT_S = 30
@dataclass(frozen=True)
class CameraSettings:
    key: str
    device: str
    width: int = 640
    height: int = 480
    fps: int = 30


@dataclass(frozen=True)
class RobotRolloutSettings:
    robot_type: str = "so101_follower"
    robot_id: str = "so101_follower"
    robot_port: str = "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A7A017797-if00"
    side_camera: str = "/dev/video0"
    top_camera: str = "/dev/video2"
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 30
    rollout_fps: float = 20
    policy_device: str = "cpu"
    return_to_initial_position: bool = False
    display_data: bool = False

    def camera_argument(self) -> str:
        cameras = {
            "side": CameraSettings(
                "side", self.side_camera, self.camera_width, self.camera_height, self.camera_fps
            ),
            "top": CameraSettings(
                "top", self.top_camera, self.camera_width, self.camera_height, self.camera_fps
            ),
        }
        return json.dumps(
            {
                camera.key: {
                    "type": "opencv",
                    "index_or_path": camera.device,
                    "width": camera.width,
                    "height": camera.height,
                    "fps": camera.fps,
                }
                for camera in cameras.values()
            },
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class SkillConfig:
    target: str
    model: str
    task: str


DEFAULT_ROLLOUT_SETTINGS = RobotRolloutSettings()
SKILL_CONFIG = {
    "place_pen_right": SkillConfig(
        target="right",
        model="/home/mikami/lerobot-v060/models/act_so101_pen_center_right_20ep_v3",#"models/act_so101_pen_center_right_5ep_v1",
        task="Pick up the pen from the center and place it into the right pen holder.",
    ),
    "place_pen_left": SkillConfig(
        target="left",
        model="/home/mikami/lerobot-v060/models/act_so101_pen_center_left_20ep_v3",#"models/act_so101_pen_center_left_5ep_v1",
        task="Pick up the pen from the center and place it into the left pen holder.",
    ),
}


def build_rollout_command(
    skill: str,
    duration_s: int = 5,
    settings: RobotRolloutSettings = DEFAULT_ROLLOUT_SETTINGS,
) -> list[str]:
    if skill not in SKILL_CONFIG:
        raise ValueError(f"Skill is not configured for robot execution: {skill}")
    if not 1 <= duration_s <= ROLLOUT_DURATION_LIMIT_S:
        raise ValueError(f"Rollout duration must be between 1 and {ROLLOUT_DURATION_LIMIT_S} seconds")

    config = SKILL_CONFIG[skill]
    rollout_executable = Path(sys.executable).with_name("lerobot-rollout")
    return [
        str(rollout_executable),
        "--strategy.type=base",
        f"--policy.path={REPO_ROOT / config.model}",
        f"--robot.type={settings.robot_type}",
        f"--robot.port={settings.robot_port}",
        f"--robot.id={settings.robot_id}",
        f"--robot.cameras={settings.camera_argument()}",
        f"--task={config.task}",
        f"--fps={settings.rollout_fps:g}",
        f"--duration={duration_s}",
        f"--device={settings.policy_device}",
        f"--policy.device={settings.policy_device}",
        f"--return_to_initial_position={str(settings.return_to_initial_position).lower()}",
        f"--display_data={str(settings.display_data).lower()}",
    ]


def execute_skill(
    skill: str,
    target: str,
    duration_s: int = 5,
    confirm: Callable[[str], bool] | None = None,
    require_confirmation: bool = True,
    settings: RobotRolloutSettings = DEFAULT_ROLLOUT_SETTINGS,
) -> str:
    config = SKILL_CONFIG.get(skill)
    if config is None or config.target != target:
        raise ValueError("Requested robot skill is not allowlisted")
    command = build_rollout_command(skill, duration_s, settings)

    if require_confirmation:
        prompt = (
            f"Run {skill} with model {config.model} for at most {duration_s}s? "
            "Type EXECUTE to confirm: "
        )
        if confirm is None:
            def confirm_with_console(message: str) -> bool:
                return input(message).strip() == "EXECUTE"

            confirm = confirm_with_console
        if not confirm(prompt):
            return "CANCELLED"

    subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=True,
    )
    return "LEROBOT_ROLLOUT_COMPLETED"
