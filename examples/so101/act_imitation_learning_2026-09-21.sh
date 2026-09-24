#!/usr/bin/env bash
set -euo pipefail

# SO-101 ACT imitation-learning workflow, created 2026-09-21.
# Usage:
#   ./examples/so101/act_imitation_learning_2026-09-21.sh record
#   ./examples/so101/act_imitation_learning_2026-09-21.sh train
#   ./examples/so101/act_imitation_learning_2026-09-21.sh rollout

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
VENV_BIN="${REPO_ROOT}/.venv/bin"

# Rerun Viewer is launched as a subprocess and must be discoverable via PATH.
export PATH="${VENV_BIN}:${PATH}"

MODE="${1:-}"
if [[ "${MODE}" != "record" && "${MODE}" != "train" && "${MODE}" != "rollout" ]]; then
    echo "Usage: $0 {record|train|rollout}" >&2
    exit 2
fi

# Stable USB serial device names for the SO-101 arms.
FOLLOWER_PORT="/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A7A017797-if00"
LEADER_PORT="/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A7A017799-if00"

# Verify these nodes with: v4l2-ctl --list-devices
FRONT_CAMERA="/dev/video0"
SIDE_CAMERA="/dev/video2"

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "ERROR: required command '$1' was not found." >&2
        exit 1
    fi
}

HF_USER="mikami235"
DATASET_NAME="${DATASET_NAME:-so101_sponge_side_matching}"
POLICY_NAME="${POLICY_NAME:-act_so101_sponge_side_matching}"
DATASET_REPO_ID="${HF_USER}/${DATASET_NAME}"
POLICY_REPO_ID="${HF_USER}/${POLICY_NAME}"
TASK="${TASK:-Move the yellow sponge to the same side of the center line as the pink sponge}"

NUM_EPISODES="${NUM_EPISODES:-50}"
EPISODE_TIME_S="${EPISODE_TIME_S:-30}"
RESET_TIME_S="${RESET_TIME_S:-10}"
TRAIN_STEPS="${TRAIN_STEPS:-20000}"
HF_JOB_TARGET="${HF_JOB_TARGET:-a10g-small}"
# Keep this relative because HF Jobs runs in a different container filesystem.
OUTPUT_DIR="${OUTPUT_DIR:-outputs/train/${POLICY_NAME}}"
CAMERAS="{front: {type: opencv, index_or_path: ${FRONT_CAMERA}, width: 640, height: 480, fps: 30, fourcc: MJPG}, side: {type: opencv, index_or_path: ${SIDE_CAMERA}, width: 640, height: 480, fps: 30, fourcc: MJPG}}"

require_executable() {
    if [[ ! -x "$1" ]]; then
        echo "ERROR: '$1' was not found or is not executable." >&2
        echo "Run 'uv sync --locked --extra core_scripts' from the repository root first." >&2
        exit 1
    fi
}

if [[ -z "${HF_USER}" ]]; then
    echo "ERROR: HF_USER is empty. Run 'hf auth login' or set HF_USER explicitly, for example: HF_USER=your_username $0 record" >&2
    exit 1
fi

case "${MODE}" in
    record)
        require_executable "${VENV_BIN}/lerobot-record"
        exec "${VENV_BIN}/lerobot-record" \
            --robot.type=so101_follower \
            --robot.port="${FOLLOWER_PORT}" \
            --robot.id=so101_follower \
            --robot.cameras="${CAMERAS}" \
            --teleop.type=so101_leader \
            --teleop.port="${LEADER_PORT}" \
            --teleop.id=so101_leader \
            --display_data=false \
            --dataset.repo_id="${DATASET_REPO_ID}" \
            --dataset.single_task="${TASK}" \
            --dataset.num_episodes="${NUM_EPISODES}" \
            --dataset.episode_time_s="${EPISODE_TIME_S}" \
            --dataset.reset_time_s="${RESET_TIME_S}" \
            --dataset.streaming_encoding=true \
            --dataset.push_to_hub=true
        ;;
    train)
        require_executable "${VENV_BIN}/lerobot-train"
        require_executable "${VENV_BIN}/hf"
        exec "${VENV_BIN}/lerobot-train" \
            --dataset.repo_id="${DATASET_REPO_ID}" \
            --policy.type=act \
            --policy.repo_id="${POLICY_REPO_ID}" \
            --policy.device=cuda \
            --output_dir="${OUTPUT_DIR}" \
            --job_name="${POLICY_NAME}" \
            --steps="${TRAIN_STEPS}" \
            --wandb.enable=true \
            --job.target="${HF_JOB_TARGET}"
        ;;
    rollout)
        require_executable "${VENV_BIN}/lerobot-rollout"
        DURATION_S="${DURATION_S:-60}"
        DISPLAY_DATA="${DISPLAY_DATA:-false}"
        exec "${VENV_BIN}/lerobot-rollout" \
            --strategy.type=base \
            --policy.path="${POLICY_REPO_ID}" \
            --robot.type=so101_follower \
            --robot.port="${FOLLOWER_PORT}" \
            --robot.id=so101_follower \
            --robot.cameras="${CAMERAS}" \
            --task="${TASK}" \
            --duration="${DURATION_S}" \
            --display_data="${DISPLAY_DATA}"
        ;;
esac