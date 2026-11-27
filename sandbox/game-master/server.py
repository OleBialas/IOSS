"""The game master: a webhook service that follows the quest of the player.

Forgejo sends the issue comment and pull request events to /hook. When an
event completes a task, an actor replies, quest-bot ticks the box in the quest
issue and names the next task. It uses only the Python standard library.
"""

import hashlib
import hmac
import json
import os
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import quest

API = "http://forgejo:3000/api/v1"
ORG = "tinystats"
REPO = "tinystats"
BOT = "quest-bot"
PORT = 8000

# One event at a time, so two events do not edit the quest issue together.
LOCK = threading.Lock()


class ApiError(Exception):
    """A request to the Forgejo API failed."""


@dataclass
class Settings:
    token: str
    secret: str
    quest_issue: int


def api(token, method, path, body=None, sudo=None):
    """Send a request to the Forgejo API and return the decoded JSON."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Content-Type", "application/json")
    if sudo:
        req.add_header("Sudo", sudo)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as err:
        raise ApiError(f"{method} {path}: {err.code} {err.read().decode()}") from err
    return json.loads(raw) if raw else None


def valid_signature(secret, body, signature):
    """Return True if the signature is the HMAC-SHA256 of the body."""
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def handle(event, payload, settings):
    """Do the task that the event completes. Return a line for the log."""
    if payload.get("repository", {}).get("full_name") != f"{ORG}/{REPO}":
        return "other repository"
    q = quest.load()
    found = quest.match(q, event, payload, settings.quest_issue)
    if found is None:
        return f"{event}: no task"
    task, number = found
    player = q["player"]
    issues = f"/repos/{ORG}/{REPO}/issues"
    quest_path = f"{issues}/{settings.quest_issue}"

    with LOCK:
        body = api(settings.token, "GET", quest_path)["body"]
        if quest.is_done(body, task["id"]):
            return f"{task['id']}: already done"

        actor = task.get("reply_as", "maintainer")
        reply = task["reply"].format(player=player).strip()
        api(settings.token, "POST", f"{issues}/{number}/comments", {"body": reply}, sudo=actor)
        if task.get("assign"):
            api(settings.token, "PATCH", f"{issues}/{number}", {"assignees": [player]}, sudo=actor)

        body = quest.tick(body, task["id"])
        api(settings.token, "PATCH", quest_path, {"body": body}, sudo=BOT)
        comment = quest.progress(q, task, body)
        api(settings.token, "POST", f"{quest_path}/comments", {"body": comment}, sudo=BOT)
    return f"{task['id']}: done on #{number}"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        settings = self.server.settings
        if self.path != "/hook":
            self.answer(404, "unknown path")
            return
        if settings is None:
            self.answer(503, "setup.py has not run yet")
            return
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if not valid_signature(settings.secret, raw, self.headers.get("X-Forgejo-Signature")):
            self.answer(403, "wrong signature")
            return
        event = self.headers.get("X-Forgejo-Event", "")
        try:
            self.answer(200, handle(event, json.loads(raw), settings))
        except ApiError as err:
            self.answer(502, str(err))

    def answer(self, code, text):
        """Send the text as the response. Forgejo shows it in the delivery log."""
        self.log_message("%s %s", code, text)
        data = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def read_settings():
    """Read the settings that setup.py writes to .env. Return None if not set."""
    token = os.environ.get("ADMIN_TOKEN")
    secret = os.environ.get("WEBHOOK_SECRET")
    quest_issue = os.environ.get("QUEST_ISSUE")
    if not (token and secret and quest_issue):
        return None
    return Settings(token, secret, int(quest_issue))


def main():
    server = ThreadingHTTPServer(("", PORT), Handler)
    server.settings = read_settings()
    if server.settings is None:
        print("No settings yet. Run setup.py.", flush=True)
    print(f"The game master listens on port {PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
