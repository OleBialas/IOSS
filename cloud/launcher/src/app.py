"""IOSS launcher: start a personal sandbox on EC2 from a web page.

One Lambda function, behind a Function URL, does three jobs:

- ``GET /`` serves the web page.
- ``/api/sessions`` starts, shows and ends sandboxes.
- The EventBridge event ``{"action": "reap"}`` terminates expired sandboxes.

Each sandbox is one EC2 instance. Its user data installs Docker and runs
``sandbox/compose.yaml`` and ``sandbox/setup.py`` from the bundle in S3. The
instance also shuts itself down at the end of its lifetime, and the launch
template turns a shutdown into a termination. The reaper is a second safety net.

The function uses only the Python standard library and boto3.
"""

import base64
import functools
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shlex
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANAGED_TAG = "ioss:managed"
EXPIRES_TAG = "ioss:expires-at"
SESSION_TAG = "ioss:session"
ACTIVE_STATES = ["pending", "running"]
SESSION_PATH = re.compile(r"^/api/sessions/([A-Za-z0-9_-]{20,64})$")
USERNAME = "newcomer"
# After this time without the seeded issues, the page says that setup failed.
SETUP_TIMEOUT = 20 * 60


def config(name, default=None):
    """Read a setting from the environment of the function."""
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"The environment variable {name} is not set")
    return value


@functools.cache
def aws(service):
    """Return a cached boto3 client. Tests replace this function."""
    import boto3
    from botocore.config import Config

    if service == "s3":
        # Sign for the regional endpoint. With the global endpoint
        # (bucket.s3.amazonaws.com), S3 rejects the URL with 400 until the
        # DNS of a new bucket outside us-east-1 has spread, which can take hours.
        region = config("AWS_REGION")
        return boto3.client(
            "s3",
            region_name=region,
            endpoint_url=f"https://s3.{region}.amazonaws.com",
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )
    return boto3.client(service)


def table():
    """Return the DynamoDB table of the sessions."""
    import boto3

    return boto3.resource("dynamodb").Table(config("TABLE_NAME"))


# --- HTTP -----------------------------------------------------------------


def respond(status, body, content_type="application/json"):
    """Build a Function URL response."""
    if content_type == "application/json":
        body = json.dumps(body)
    return {
        "statusCode": status,
        "headers": {"Content-Type": content_type, "Cache-Control": "no-store"},
        "body": body,
    }


def read_json(event):
    """Return the JSON body of a request, or an empty dict."""
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    try:
        body = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return body if isinstance(body, dict) else {}


def handler(event, context):
    """Entry point for the Function URL and the reaper schedule."""
    if event.get("action") == "reap":
        return {"terminated": reap()}

    try:
        return route(event)
    except Exception as err:
        # Log the full error for the instructor. Show the learner only the
        # AWS error code, never the message, which can contain ARNs.
        logging.exception("Request failed")
        response = getattr(err, "response", None)
        code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
        detail = f" ({code})" if code else ""
        return respond(
            500,
            {"error": f"The launcher failed{detail}. Ask your instructor."},
        )


def route(event):
    """Answer one request of the Function URL."""
    method = event["requestContext"]["http"]["method"]
    path = event.get("rawPath", "/")

    if method == "GET" and path == "/":
        page = (HERE / "index.html").read_text()
        return respond(200, page, "text/html; charset=utf-8")
    if method == "POST" and path == "/api/sessions":
        return start_session(read_json(event))
    match = SESSION_PATH.match(path)
    if match and method == "GET":
        return show_session(match.group(1))
    if match and method == "DELETE":
        return end_session(match.group(1))
    return respond(404, {"error": "Not found"})


# --- Sessions -------------------------------------------------------------


def start_session(body):
    """Check the access code and the limit, then launch a sandbox."""
    code = str(body.get("code", ""))
    if not hmac.compare_digest(code.encode(), config("ACCESS_CODE").encode()):
        return respond(403, {"error": "The access code is wrong."})

    limit = int(config("MAX_SESSIONS", "10"))
    if len(active_instances()) >= limit:
        return respond(
            503,
            {"error": f"All {limit} sandboxes are in use. Try again later."},
        )

    session_id = secrets.token_urlsafe(24)
    password = secrets.token_urlsafe(12)
    minutes = int(config("SESSION_MINUTES", "180"))
    now = int(time.time())
    expires_at = now + minutes * 60

    instance = aws("ec2").run_instances(
        LaunchTemplate={
            "LaunchTemplateId": config("LAUNCH_TEMPLATE_ID"),
            "Version": "$Latest",
        },
        MinCount=1,
        MaxCount=1,
        UserData=user_data(bundle_url(), password, minutes),
        TagSpecifications=[
            {
                "ResourceType": kind,
                "Tags": [
                    {"Key": "Name", "Value": f"{config('NAME_PREFIX', 'ioss')}-sandbox"},
                    {"Key": MANAGED_TAG, "Value": "true"},
                    {"Key": EXPIRES_TAG, "Value": str(expires_at)},
                    # A hash, so the tag does not give away the session.
                    {"Key": SESSION_TAG, "Value": session_hash(session_id)},
                ],
            }
            for kind in ("instance", "volume")
        ],
    )["Instances"][0]

    table().put_item(
        Item={
            "session_id": session_id,
            "instance_id": instance["InstanceId"],
            "password": password,
            "created_at": now,
            "expires_at": expires_at,
            # DynamoDB deletes the item one day after the sandbox ends.
            "ttl": expires_at + 24 * 3600,
        }
    )
    return respond(201, {"session": session_id, "expires_at": expires_at})


def show_session(session_id):
    """Report the state of a sandbox and, once ready, how to log in."""
    item = table().get_item(Key={"session_id": session_id}).get("Item")
    if not item:
        return respond(404, {"error": "This session does not exist."})

    now = int(time.time())
    created_at = int(item["created_at"])
    expires_at = int(item["expires_at"])
    result = {"expires_at": expires_at, "created_at": created_at, "now": now}

    instance = describe(item["instance_id"])
    state = instance["State"]["Name"] if instance else "terminated"
    host = (instance or {}).get("PublicDnsName")

    if item.get("ended") or state not in ACTIVE_STATES or now >= expires_at:
        return respond(200, {**result, "status": "ended"})
    if state == "pending" or not host:
        return respond(200, {**result, "status": "starting"})

    ready = bool(item.get("ready")) or is_ready(host)
    if not ready:
        status = "failed" if now - created_at > SETUP_TIMEOUT else "installing"
        return respond(200, {**result, "status": status})

    if not item.get("ready"):
        table().update_item(
            Key={"session_id": session_id},
            UpdateExpression="SET ready = :t",
            ExpressionAttributeValues={":t": True},
        )
    base = f"http://{host}:3000"
    return respond(
        200,
        {
            **result,
            "status": "ready",
            "forgejo_url": base,
            "repo_url": f"{base}/{repo_path()}",
            "clone_url": f"{base}/{repo_path()}.git",
            "username": USERNAME,
            "password": item["password"],
        },
    )


def end_session(session_id):
    """Terminate the sandbox of a session."""
    item = table().get_item(Key={"session_id": session_id}).get("Item")
    if not item:
        return respond(404, {"error": "This session does not exist."})
    terminate([item["instance_id"]])
    table().update_item(
        Key={"session_id": session_id},
        UpdateExpression="SET ended = :t",
        ExpressionAttributeValues={":t": True},
    )
    return respond(200, {"status": "ended"})


def reap(now=None):
    """Terminate every sandbox after its lifetime. Return their IDs."""
    now = now or int(time.time())
    expired = []
    for instance in active_instances():
        tags = {t["Key"]: t["Value"] for t in instance.get("Tags", [])}
        try:
            expires_at = int(tags.get(EXPIRES_TAG, "0"))
        except ValueError:
            expires_at = 0
        if expires_at <= now:
            expired.append(instance["InstanceId"])
    terminate(expired)
    return expired


# --- EC2 and S3 -----------------------------------------------------------


def active_instances():
    """Return the pending and running sandbox instances."""
    instances = []
    paginator = aws("ec2").get_paginator("describe_instances")
    for page in paginator.paginate(
        Filters=[
            {"Name": f"tag:{MANAGED_TAG}", "Values": ["true"]},
            {"Name": "instance-state-name", "Values": ACTIVE_STATES},
        ]
    ):
        for reservation in page["Reservations"]:
            instances.extend(reservation["Instances"])
    return instances


def describe(instance_id):
    """Return one instance, or None when EC2 no longer knows it."""
    try:
        reservations = aws("ec2").describe_instances(InstanceIds=[instance_id])[
            "Reservations"
        ]
    except Exception as err:  # botocore ClientError: InvalidInstanceID.NotFound
        if "InvalidInstanceID" in str(err):
            return None
        raise
    for reservation in reservations:
        for instance in reservation["Instances"]:
            return instance
    return None


def terminate(instance_ids):
    """Terminate instances. The IAM policy allows only sandbox instances."""
    if instance_ids:
        aws("ec2").terminate_instances(InstanceIds=instance_ids)


def bundle_url():
    """Return a short-lived download URL for the sandbox bundle."""
    return aws("s3").generate_presigned_url(
        "get_object",
        Params={"Bucket": config("BUNDLE_BUCKET"), "Key": config("BUNDLE_KEY")},
        ExpiresIn=3600,
    )


def user_data(url, password, minutes):
    """Fill in the boot script of a sandbox instance."""
    script = (HERE / "user_data.sh").read_text()
    values = {
        "__BUNDLE_URL__": shlex.quote(url),
        "__NEWCOMER_PASSWORD__": shlex.quote(password),
        "__MINUTES__": str(int(minutes)),
    }
    for placeholder, value in values.items():
        script = script.replace(placeholder, value)
    return script


def session_hash(session_id):
    """Return a short, non-reversible tag value for a session."""
    return hashlib.sha256(session_id.encode()).hexdigest()[:16]


# --- Readiness ------------------------------------------------------------


def repo_path():
    """Return the path of the practice repository on Forgejo."""
    return config("REPO_PATH", "tinystats/tinystats")


def is_ready(host, timeout=3):
    """Check that setup.py has created all seeded issues.

    setup.py creates the issues last, after the users and the repository, so
    the count of issues tells whether setup is complete.
    """
    url = (
        f"http://{host}:3000/api/v1/repos/{repo_path()}/issues"
        "?state=all&type=issues&limit=50"
    )
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            issues = json.load(resp)
    except Exception:
        return False
    return isinstance(issues, list) and len(issues) >= int(config("SEED_ISSUES", "1"))
