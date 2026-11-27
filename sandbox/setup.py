"""Populate a fresh Forgejo sandbox for the first-contribution scenario.

The script creates the actors, the tinystats organisation and repository, the
seeded code and the issues. It uses only the Python standard library.

Usage:
    docker compose up -d
    python3 setup.py [--source PATH_OR_URL]
"""

import argparse
import base64
import json
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "http://localhost:3000"
ORG = "tinystats"
REPO = "tinystats"
DEFAULT_SOURCE = "https://github.com/florence-bockting/tinystats"

HERE = Path(__file__).resolve().parent
SEED = HERE.parent / "seed"
ENV_FILE = HERE / ".env"

ADMIN = "ioss-admin"
# Each actor and its permission on the repository. None means read only.
ACTORS = {
    "maintainer": "admin",
    "reviewer": "write",
    "newcomer": "write",
    "fellow": None,
    "ci-bot": "write",
}
LABELS = {
    "bug": ("#d73a4a", "Something does not work"),
    "documentation": ("#0075ca", "Changes to the documentation"),
    "good first issue": ("#7057ff", "Good for newcomers"),
}


def api(method, path, token, body=None, sudo=None, ok_codes=(200, 201, 204)):
    """Send a request to the Forgejo API and return the decoded JSON."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{URL}/api/v1{path}", data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Content-Type", "application/json")
    if sudo:
        req.add_header("Sudo", sudo)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as err:
        if err.code in ok_codes:
            return None
        sys.exit(f"{method} {path} failed: {err.code} {err.read().decode()}")
    return json.loads(raw) if raw else None


def wait_for_forgejo(timeout=60):
    """Wait until the Forgejo API answers."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{URL}/api/v1/version")
            return
        except (urllib.error.URLError, ConnectionError):
            time.sleep(2)
    sys.exit(f"Forgejo does not answer at {URL}. Run `docker compose up -d`.")


def forgejo_cli(*args):
    """Run the forgejo CLI in the container as the git user."""
    cmd = ["docker", "compose", "exec", "-T", "-u", "git", "forgejo", "forgejo"]
    result = subprocess.run(
        [*cmd, *args], cwd=HERE, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        sys.exit(f"forgejo {' '.join(args[:3])} failed:\n{result.stderr}")
    return result.stdout.strip()


def read_issue(path):
    """Read the front matter and the body of an issue file."""
    _, front, body = path.read_text().split("---\n", 2)
    meta = {}
    for line in front.splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith("["):
            meta[key] = [v.strip() for v in value.strip("[]").split(",")]
        else:
            meta[key] = value.strip('"')
    return meta, body.strip()


def push_seeded_repo(source, token):
    """Push the seeded tinystats as one commit, so git log shows no bugs."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / REPO
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1", source, str(work)], check=True
        )
        patches = sorted(str(p) for p in (SEED / "patches").glob("*.patch"))
        subprocess.run(["git", "apply", *patches], cwd=work, check=True)
        subprocess.run(["rm", "-rf", str(work / ".git")], check=True)

        auth = base64.b64encode(f"{ADMIN}:{token}".encode()).decode()
        git = [
            "git",
            "-c", "user.name=maintainer",
            "-c", "user.email=maintainer@ioss.test",
            "-c", f"http.extraHeader=Authorization: Basic {auth}",
        ]  # fmt: skip
        for step in (
            ["init", "-q", "-b", "main"],
            ["add", "-A"],
            ["commit", "-q", "-m", "Initial version of tinystats"],
            ["push", "-q", f"{URL}/{ORG}/{REPO}.git", "main"],
        ):
            subprocess.run([*git, *step], cwd=work, check=True)


def main():
    """Create the actors, the repository and the issues."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help="clean tinystats to clone (path or URL)",
    )
    args = parser.parse_args()

    wait_for_forgejo()
    if ENV_FILE.exists():
        sys.exit(f"{ENV_FILE} exists. Reset with `docker compose down -v` first.")

    passwords = {name: secrets.token_urlsafe(12) for name in [ADMIN, *ACTORS]}
    forgejo_cli(
        "admin", "user", "create", "--admin",
        "--username", ADMIN,
        "--email", f"{ADMIN}@ioss.test",
        "--password", passwords[ADMIN],
    )  # fmt: skip
    token = forgejo_cli(
        "admin", "user", "generate-access-token",
        "--username", ADMIN,
        "--token-name", "setup",
        "--scopes", "all",
        "--raw",
    )  # fmt: skip

    for name in ACTORS:
        api("POST", "/admin/users", token, {
            "username": name,
            "email": f"{name}@ioss.test",
            "password": passwords[name],
            "must_change_password": False,
        })  # fmt: skip
    print(f"Created users: {', '.join(ACTORS)}")

    api("POST", "/orgs", token, {"username": ORG, "visibility": "public"})
    api("POST", f"/orgs/{ORG}/repos", token, {"name": REPO, "default_branch": "main"})
    for name, permission in ACTORS.items():
        if permission:
            api(
                "PUT",
                f"/repos/{ORG}/{REPO}/collaborators/{name}",
                token,
                {"permission": permission},
            )
    print(f"Created repository: {URL}/{ORG}/{REPO}")

    push_seeded_repo(args.source, token)
    print("Pushed the seeded code")

    label_ids = {}
    for name, (color, description) in LABELS.items():
        label = api(
            "POST",
            f"/repos/{ORG}/{REPO}/labels",
            token,
            {"name": name, "color": color, "description": description},
        )
        label_ids[name] = label["id"]

    for path in sorted((SEED / "issues").glob("*.md")):
        meta, body = read_issue(path)
        issue = api(
            "POST",
            f"/repos/{ORG}/{REPO}/issues",
            token,
            {"title": meta["title"], "body": body},
            sudo="fellow",
        )
        api(
            "POST",
            f"/repos/{ORG}/{REPO}/issues/{issue['number']}/labels",
            token,
            {"labels": [label_ids[name] for name in meta["labels"]]},
        )
        print(f"Created issue #{issue['number']}: {meta['title']}")

    lines = [f"FORGEJO_URL={URL}", f"ADMIN_TOKEN={token}"]
    lines += [
        f"{n.upper().replace('-', '_')}_PASSWORD={p}" for n, p in passwords.items()
    ]
    ENV_FILE.write_text("\n".join(lines) + "\n")
    ENV_FILE.chmod(0o600)
    print(f"Wrote the test passwords to {ENV_FILE}")


if __name__ == "__main__":
    main()
