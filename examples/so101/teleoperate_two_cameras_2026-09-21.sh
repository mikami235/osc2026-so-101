#!/usr/bin/env bash
set -euo pipefail

# Run SO-101 teleoperation with two USB cameras and display both images in Rerun.
# This script expects the uv-managed virtual environment at the repository root:
#   /home/mikami/lerobot-v060/.venv

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
VENV_BIN="${REPO_ROOT}/.venv/bin"
LEROBOT_TELEOPERATE="${REPO_ROOT}/.venv/bin/lerobot-teleoperate"

# Rerun Viewer is launched as a subprocess and must be discoverable via PATH.
export PATH="${VENV_BIN}:${PATH}"

if [[ ! -x "${LEROBOT_TELEOPERATE}" ]]; then
    echo "ERROR: ${LEROBOT_TELEOPERATE} was not found or is not executable." >&2
    echo "Run 'uv sync --locked --extra core_scripts' from the repository root first." >&2
    exit 1
fi

# USB serial devices for the robot arms.
# FOLLOWER_PORT is the SO-101 follower arm: the arm that physically moves.
# LEADER_PORT is the SO-101 leader arm: the arm operated by the user.
# The /dev/serial/by-id paths are stable device names and are safer than
# /dev/ttyACM0 and /dev/ttyACM1, which can swap after reconnecting USB devices.
FOLLOWER_PORT="/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A7A017797-if00"
LEADER_PORT="/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A7A017799-if00"

# USB camera devices exposed by Linux V4L2.
# /dev/video0 is the Web Camera used as the front camera.
# /dev/video2 is the EMEET SmartCam C960 used as the side camera.
# /dev/video1 and /dev/video3 are additional nodes exposed by those cameras;
# they are not separate physical cameras and are not used here.
# /dev/videoN numbers can change after reconnecting or rebooting, so verify
# them with: v4l2-ctl --list-devices
FRONT_CAMERA="/dev/video0"
SIDE_CAMERA="/dev/video2"

exec "${LEROBOT_TELEOPERATE}" \
    --robot.type=so101_follower \
    --robot.port="${FOLLOWER_PORT}" \
    --robot.id=so101_follower \
    --teleop.type=so101_leader \
    --teleop.port="${LEADER_PORT}" \
    --teleop.id=so101_leader \
    --robot.cameras="{front: {type: opencv, index_or_path: ${FRONT_CAMERA}, width: 640, height: 480, fps: 30}, side: {type: opencv, index_or_path: ${SIDE_CAMERA}, width: 640, height: 480, fps: 30, fourcc: MJPG}}" \
    --display_data=true
