"""The quest: the tasks, the checklist and the match of events to tasks.

setup.py and server.py both use this module. It uses only the Python standard
library.
"""

import re
import tomllib
from pathlib import Path

QUESTS_FILE = Path(__file__).resolve().parent / "quests.toml"


def load(path=QUESTS_FILE):
    """Read the quest from the TOML file."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def marker(task_id):
    """Return the hidden marker that identifies the checklist line of a task."""
    return f"<!-- task:{task_id} -->"


def render_body(quest):
    """Return the body of the quest issue: the intro and the checklist."""
    lines = [quest["intro"].format(player=quest["player"]).strip(), ""]
    lines += [f"- [ ] {task['text']} {marker(task['id'])}" for task in quest["task"]]
    return "\n".join(lines) + "\n"


def is_done(body, task_id):
    """Return True if the box of the task is ticked."""
    pattern = rf"^- \[[xX]\] .*{re.escape(marker(task_id))}"
    return re.search(pattern, body, re.MULTILINE) is not None


def tick(body, task_id):
    """Return the body with the box of the task ticked."""
    pattern = rf"^- \[ \] (.*{re.escape(marker(task_id))})"
    return re.sub(pattern, r"- [x] \1", body, flags=re.MULTILINE)


def progress(quest, task, body):
    """Return the quest-bot comment after a task is done."""
    done = f"Task done: {task['text']}"
    following = [t for t in quest["task"] if not is_done(body, t["id"])]
    active = [t for t in following if "trigger" in t]
    if not active:
        return f"{done}\n\n{quest['finish']}"
    lines = [done, "", f"Next task: {following[0]['text']}"]
    if following[0].get("hint"):
        lines += ["", following[0]["hint"]]
    return "\n".join(lines)


def target(event, payload, quest_issue):
    """Return the number of the issue or pull request that an event is about.

    Return None if no task can use the event.
    """
    if event == "issue_comment":
        issue = payload["issue"]
        if payload.get("is_pull") or issue["number"] == quest_issue:
            return None
        return issue["number"]
    if event == "pull_request":
        return payload["pull_request"]["number"]
    return None


def match(quest, event, payload, quest_issue):
    """Return the task that an event completes and the target number, or None."""
    if payload.get("sender", {}).get("login") != quest["player"]:
        return None
    number = target(event, payload, quest_issue)
    if number is None:
        return None
    for task in quest["task"]:
        trigger = task.get("trigger")
        if trigger == {"event": event, "action": payload.get("action")}:
            return task, number
    return None
