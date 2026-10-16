"""API-free assistant used to exercise the text routing flow locally."""

from typing import Any


class MockAssistant:
    def classify_action(self, instruction: str) -> dict[str, Any]:
        has_right = "右" in instruction
        has_left = "左" in instruction
        if has_right == has_left:
            return {"skill": "none", "target": None}
        if has_right:
            return {"skill": "place_pen_right", "target": "right"}
        return {"skill": "place_pen_left", "target": "left"}

    def reply(self, message: str) -> str:
        return f"[MOCK conversation] {message}"
