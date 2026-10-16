# SO-101 Voice Skill Router

The CLI supports Japanese text and microphone input. Normal conversation uses OpenAI for the reply and speech output. Only utterances beginning with `アクション` enter the allowlisted pen-placement router.

## Dry-run

Text-only mock mode does not require an API key and never connects to the robot:

```bash
uv run --extra voice --extra test python -m examples.so101.voice_skill_router.cli --text 'アクション。右に入れて' --mock
```

For microphone input and OpenAI transcription, intent routing, and spoken conversation, set `OPENAI_API_KEY` in the shell and run without `--mock`:

```bash
uv run --extra voice --extra test python -m examples.so101.voice_skill_router.cli --mic --duration 5
```

## Confirmed Robot Mode

The robot is disabled by default. For repeated voice interactions, start one microphone session with explicit robot opt-in:

```bash
uv run --extra voice --extra test python -m examples.so101.voice_skill_router.cli \
  --mic --loop --duration 5 --enable-robot --rollout-duration 5
```

The first recording starts immediately. After each result, press Enter to record the next utterance or `q` to exit. Only an allowlisted action is eligible to run. The default `--confirmation-mode required` asks for `EXECUTE` before each rollout. To disable that prompt, explicitly pass `--confirmation-mode none`; `--enable-robot` is still required and a warning is printed at startup:

```bash
uv run --extra voice --extra test python -m examples.so101.voice_skill_router.cli \
  --mic --loop --duration 5 --enable-robot --rollout-duration 5 --confirmation-mode none
```

Each skill maps to a fixed local model and task, runs on CPU, and is capped at 30 seconds (5 seconds by default). LLM output is never used to construct rollout arguments.

## Hardware Options

The default hardware profile matches the tested setup: robot port `/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A7A017797-if00`, camera keys `side=/dev/video0` and `top=/dev/video2`, 640x480 at 30 camera FPS, 20 rollout FPS, and CPU inference. These values can be overridden by `--robot-port`, `--side-camera`, `--top-camera`, `--camera-width`, `--camera-height`, `--camera-fps`, `--rollout-fps`, and `--policy-device`. Microphone options are `--record-duration` and `--microphone-device`; the previous `--duration` and `--device` spellings remain aliases.

Confirm the camera nodes still correspond to the views used to collect the model data before enabling robot mode. `--rollout-fps` is the requested control-loop rate, not a performance accelerator. In the reported CPU run, inference reached about 1.2 Hz against a 20 Hz target; lowering the target does not make inference faster and changes runtime action cadence. Keep the actual LeRobot warnings visible and assess motion carefully.

Rollout teardown is configured not to move the arm back to its startup pose. The robot disconnects at the end of each rollout, so keep the workspace clear and supervise the arm throughout. Use Ctrl+C to stop the voice session. This example does not provide a hardware emergency-stop mechanism.
