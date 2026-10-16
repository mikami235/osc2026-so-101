"""Conversation/action routing and strict validation of model-selected skills."""

from dataclasses import dataclass
from typing import Any, Callable

ALLOWED_SKILLS = {"place_pen_right", "place_pen_left", "none"}
SKILL_TARGETS = {"place_pen_right": "right", "place_pen_left": "left"}


@dataclass(frozen=True)
class RouteResult:
    recognized: str
    conversation: str | None = None
    skill: str | None = None
    mode: str = "DRY-RUN"
    result: str | None = None


def extract_action_instruction(text: str) -> str | None:
    """Only a leading explicit 'アクション' phrase can enter skill routing."""
    stripped = text.strip()
    if not stripped.startswith("アクション"):
        return None
    remainder = stripped[len("アクション") :].lstrip(" \t、。,:：")
    return remainder


def validate_intent(intent: Any) -> tuple[str, str | None]:
    if not isinstance(intent, dict) or set(intent) != {"skill", "target"}:
        raise ValueError("Invalid skill intent shape")
    skill = intent["skill"]
    target = intent["target"]
    if skill not in ALLOWED_SKILLS:
        raise ValueError("Skill is not allowlisted")
    if skill == "none":
        if target is not None:
            raise ValueError("Target must be null when skill is none")
    elif target != SKILL_TARGETS[skill]:
        raise ValueError("Skill and target do not match")
    return skill, target


def route_text(
    text: str,
    assistant: Any,
    dispatch: Callable[[str, str], str],
) -> RouteResult:
    instruction = extract_action_instruction(text)
    if instruction is None:
        return RouteResult(recognized=text, conversation=assistant.reply(text))

    if not instruction:
        return RouteResult(recognized=text, skill="none", result="NO_ACTION")

    skill, target = validate_intent(assistant.classify_action(instruction))
    if skill == "none":
        return RouteResult(recognized=text, skill=skill, result="NO_ACTION")
    if target is None:
        raise ValueError("A selected skill requires a target")
    result = dispatch(skill, target)
    return RouteResult(recognized=text, skill=skill, result=result)