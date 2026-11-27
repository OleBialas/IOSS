"""Tests for the launcher. Fakes replace EC2, S3 and DynamoDB."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import app  # noqa: E402

CODE = "workshop-code"


class FakeEC2:
    def __init__(self):
        self.instances = {}
        self.launched = []
        self.terminated = []

    def run_instances(self, **kwargs):
        self.launched.append(kwargs)
        instance_id = f"i-{len(self.instances):04d}"
        tags = kwargs["TagSpecifications"][0]["Tags"]
        self.instances[instance_id] = {
            "InstanceId": instance_id,
            "State": {"Name": "pending"},
            "PublicDnsName": "",
            "Tags": tags,
        }
        return {"Instances": [self.instances[instance_id]]}

    def describe_instances(self, InstanceIds=None, Filters=None):
        found = [self.instances[i] for i in InstanceIds or self.instances]
        if Filters:
            states = next(f["Values"] for f in Filters if f["Name"] == "instance-state-name")
            found = [i for i in found if i["State"]["Name"] in states]
        return {"Reservations": [{"Instances": found}]}

    def get_paginator(self, name):
        fake = self

        class Paginator:
            def paginate(self, **kwargs):
                yield fake.describe_instances(**kwargs)

        return Paginator()

    def terminate_instances(self, InstanceIds):
        self.terminated.extend(InstanceIds)
        for i in InstanceIds:
            self.instances[i]["State"]["Name"] = "shutting-down"


class FakeS3:
    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"https://s3.example/{Params['Key']}?X-Amz-Signature=a&b=c"


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        self.items[Item["session_id"]] = dict(Item)

    def get_item(self, Key):
        item = self.items.get(Key["session_id"])
        return {"Item": dict(item)} if item else {}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues):
        attr = UpdateExpression.split()[1]
        self.items[Key["session_id"]][attr] = ExpressionAttributeValues[":t"]


@pytest.fixture
def fakes(monkeypatch):
    ec2, s3, table = FakeEC2(), FakeS3(), FakeTable()
    monkeypatch.setattr(app, "aws", lambda service: {"ec2": ec2, "s3": s3}[service])
    monkeypatch.setattr(app, "table", lambda: table)
    monkeypatch.setattr(app, "is_ready", lambda host: False)
    for key, value in {
        "ACCESS_CODE": CODE,
        "MAX_SESSIONS": "2",
        "SESSION_MINUTES": "60",
        "LAUNCH_TEMPLATE_ID": "lt-123",
        "BUNDLE_BUCKET": "bucket",
        "BUNDLE_KEY": "bundle.zip",
        "TABLE_NAME": "sessions",
        "SEED_ISSUES": "3",
    }.items():
        monkeypatch.setenv(key, value)
    return ec2, table


def request(method, path, body=None):
    event = {"requestContext": {"http": {"method": method}}, "rawPath": path}
    if body is not None:
        event["body"] = json.dumps(body)
    response = app.handler(event, None)
    if response["headers"]["Content-Type"] == "application/json":
        return response["statusCode"], json.loads(response["body"])
    return response["statusCode"], response["body"]


def start():
    return request("POST", "/api/sessions", {"code": CODE})


def test_page_is_served(fakes):
    status, body = request("GET", "/")
    assert status == 200
    assert "Start my sandbox" in body


def test_unknown_route(fakes):
    assert request("GET", "/nope")[0] == 404


@pytest.mark.parametrize("body", [{"code": "wrong"}, {}, {"code": 123}])
def test_wrong_access_code_launches_nothing(fakes, body):
    ec2, _ = fakes
    status, data = request("POST", "/api/sessions", body)
    assert status == 403
    assert ec2.launched == []


def test_start_launches_tagged_instance(fakes):
    ec2, table = fakes
    status, data = start()
    assert status == 201
    launch = ec2.launched[0]
    assert launch["LaunchTemplate"]["LaunchTemplateId"] == "lt-123"
    tags = {t["Key"]: t["Value"] for t in launch["TagSpecifications"][0]["Tags"]}
    assert tags["ioss:managed"] == "true"
    assert int(tags["ioss:expires-at"]) == data["expires_at"]
    assert data["session"] not in tags.values()

    item = table.items[data["session"]]
    assert item["instance_id"] == "i-0000"
    assert item["password"] in launch["UserData"]
    assert "shutdown -h +60" in launch["UserData"]


def test_limit_of_active_sessions(fakes):
    ec2, _ = fakes
    assert start()[0] == 201
    assert start()[0] == 201
    status, data = start()
    assert status == 503
    assert "2 sandboxes" in data["error"]
    # An ended sandbox frees a slot.
    ec2.terminate_instances(["i-0000"])
    assert start()[0] == 201


def test_session_lifecycle(fakes, monkeypatch):
    ec2, table = fakes
    session = start()[1]["session"]
    path = f"/api/sessions/{session}"

    assert request("GET", path)[1]["status"] == "starting"

    ec2.instances["i-0000"].update(
        State={"Name": "running"}, PublicDnsName="ec2-1-2-3-4.example"
    )
    status, data = request("GET", path)
    assert data["status"] == "installing"
    assert "password" not in data

    monkeypatch.setattr(app, "is_ready", lambda host: True)
    data = request("GET", path)[1]
    assert data["status"] == "ready"
    assert data["repo_url"] == "http://ec2-1-2-3-4.example:3000/tinystats/tinystats"
    assert data["username"] == "newcomer"
    assert data["password"] == table.items[session]["password"]
    assert table.items[session]["ready"] is True

    # Once ready, the launcher does not probe again.
    monkeypatch.setattr(app, "is_ready", lambda host: pytest.fail("probed again"))
    assert request("GET", path)[1]["status"] == "ready"

    assert request("DELETE", path)[0] == 200
    assert ec2.terminated == ["i-0000"]
    assert request("GET", path)[1]["status"] == "ended"


def test_setup_timeout(fakes, monkeypatch):
    ec2, table = fakes
    session = start()[1]["session"]
    ec2.instances["i-0000"].update(State={"Name": "running"}, PublicDnsName="h")
    table.items[session]["created_at"] -= app.SETUP_TIMEOUT + 1
    assert request("GET", f"/api/sessions/{session}")[1]["status"] == "failed"


def test_expired_session_is_ended(fakes):
    ec2, table = fakes
    session = start()[1]["session"]
    ec2.instances["i-0000"].update(State={"Name": "running"}, PublicDnsName="h")
    table.items[session]["expires_at"] = 0
    assert request("GET", f"/api/sessions/{session}")[1]["status"] == "ended"


def test_unknown_session(fakes):
    assert request("GET", "/api/sessions/" + "x" * 32)[0] == 404
    assert request("DELETE", "/api/sessions/" + "x" * 32)[0] == 404


def test_reaper_terminates_only_expired(fakes):
    ec2, _ = fakes
    start()
    start()
    ec2.instances["i-0000"]["Tags"] = [
        {"Key": "ioss:managed", "Value": "true"},
        {"Key": "ioss:expires-at", "Value": "100"},
    ]
    assert app.handler({"action": "reap"}, None) == {"terminated": ["i-0000"]}
    assert ec2.terminated == ["i-0000"]


def test_aws_error_becomes_json(fakes, monkeypatch):
    class ClientError(Exception):
        response = {"Error": {"Code": "UnauthorizedOperation", "Message": "arn:..."}}

    def fail(**kwargs):
        raise ClientError("denied")

    ec2, _ = fakes
    monkeypatch.setattr(ec2, "run_instances", fail)
    status, data = start()
    assert status == 500
    assert "UnauthorizedOperation" in data["error"]
    assert "arn" not in data["error"]


def test_user_data_quotes_values(tmp_path):
    script = app.user_data("https://x/b.zip?a=1&b=$(reboot)", "p'w", 90)
    assert "__" not in script
    assert "'https://x/b.zip?a=1&b=$(reboot)'" in script
    assert "IOSS_NEWCOMER_PASSWORD='p'\"'\"'w'" in script
    path = tmp_path / "user_data.sh"
    path.write_text(script)
    subprocess.run(["bash", "-n", str(path)], check=True)
