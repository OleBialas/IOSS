"""Tests for quest.py and server.py.

Run them in sandbox/game-master:
    python3 -m unittest
"""

import hashlib
import hmac
import unittest
from unittest import mock

import quest
import server

QUEST_ISSUE = 4


def comment_event(sender="newcomer", number=2, is_pull=False):
    return {
        "action": "created",
        "is_pull": is_pull,
        "issue": {"number": number},
        "sender": {"login": sender},
        "repository": {"full_name": "tinystats/tinystats"},
    }


class QuestTest(unittest.TestCase):
    def setUp(self):
        self.quest = quest.load()
        self.body = quest.render_body(self.quest)

    def test_body_has_one_open_box_for_each_task(self):
        self.assertEqual(self.body.count("- [ ] "), len(self.quest["task"]))
        self.assertIn("@newcomer", self.body)
        self.assertIn("(+1 XP)", self.body)

    def test_tick_ticks_only_its_task(self):
        body = quest.tick(self.body, "comment-on-issue")
        self.assertTrue(quest.is_done(body, "comment-on-issue"))
        self.assertFalse(quest.is_done(body, "open-pull-request"))
        self.assertEqual(body.count("- [x] "), 1)

    def test_tick_works_with_windows_line_endings(self):
        body = quest.tick(self.body.replace("\n", "\r\n"), "comment-on-issue")
        self.assertTrue(quest.is_done(body, "comment-on-issue"))

    def test_comment_by_player_matches_task(self):
        task, number = quest.match(self.quest, "issue_comment", comment_event(), QUEST_ISSUE)
        self.assertEqual(task["id"], "comment-on-issue")
        self.assertEqual(number, 2)

    def test_comment_by_other_actor_does_not_match(self):
        event = comment_event(sender="maintainer")
        self.assertIsNone(quest.match(self.quest, "issue_comment", event, QUEST_ISSUE))

    def test_comment_on_quest_issue_does_not_match(self):
        event = comment_event(number=QUEST_ISSUE)
        self.assertIsNone(quest.match(self.quest, "issue_comment", event, QUEST_ISSUE))

    def test_comment_on_pull_request_does_not_match(self):
        event = comment_event(is_pull=True)
        self.assertIsNone(quest.match(self.quest, "issue_comment", event, QUEST_ISSUE))

    def test_progress_names_next_open_task(self):
        task = self.quest["task"][0]
        body = quest.tick(self.body, task["id"])
        text = quest.progress(self.quest, task, body)
        self.assertIn("Next task: " + self.quest["task"][1]["text"], text)

    def test_progress_awards_points_and_badge_after_goal_tasks(self):
        body = self.body
        contributor_tasks = [
            task for task in self.quest["task"] if task["badge"] == "Contributor"
        ]
        for task in contributor_tasks:
            body = quest.tick(body, task["id"])
        text = quest.progress(self.quest, contributor_tasks[-1], body)
        self.assertIn("Quest XP: 6 points", text)
        self.assertIn("Badges: Contributor", text)
        self.assertNotIn("Responder", text)

    def test_progress_awards_points_even_when_review_needs_revision(self):
        body = self.body
        responder_tasks = [
            task for task in self.quest["task"] if task["badge"] == "Responder"
        ]
        for task in responder_tasks[:2]:
            body = quest.tick(body, task["id"])
        text = quest.progress(self.quest, responder_tasks[1], body)
        self.assertIn("Quest XP: 4 points", text)
        self.assertIn("Badges: none yet", text)
        self.assertNotIn(self.quest["finish"], text)

    def test_progress_finishes_only_when_all_tasks_are_done(self):
        body = self.body
        for task in self.quest["task"][:-1]:
            body = quest.tick(body, task["id"])
        text = quest.progress(self.quest, self.quest["task"][-2], body)
        self.assertNotIn(self.quest["finish"], text)
        body = quest.tick(body, self.quest["task"][-1]["id"])
        text = quest.progress(self.quest, self.quest["task"][-1], body)
        self.assertIn(self.quest["finish"], text)
        self.assertIn("Badges: Contributor, Responder", text)


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.settings = server.Settings("token", "secret", QUEST_ISSUE)
        self.body = quest.render_body(quest.load())

    def fake_api(self, token, method, path, body=None, sudo=None):
        """Store the requests. Answer a GET of the quest issue with self.body."""
        self.calls.append((method, path, sudo))
        if method == "POST":
            self.post_bodies.append((path, body))
        if method == "GET":
            return {"body": self.body}
        if method == "PATCH" and path.endswith(f"/{QUEST_ISSUE}"):
            self.body = body["body"]
        return {}

    def run_event(self, event, payload):
        self.calls = []
        self.post_bodies = []
        with mock.patch.object(server, "api", self.fake_api):
            return server.handle(event, payload, self.settings)

    def test_signature(self):
        body = b'{"action": "created"}'
        good = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
        self.assertTrue(server.valid_signature("secret", body, good))
        self.assertFalse(server.valid_signature("secret", body, "0" * 64))
        self.assertFalse(server.valid_signature("secret", body, None))

    def test_task_replies_assigns_and_ticks(self):
        result = self.run_event("issue_comment", comment_event())
        self.assertEqual(result, "comment-on-issue: done on #2")
        self.assertEqual(
            self.calls,
            [
                ("GET", "/repos/tinystats/tinystats/issues/4", None),
                ("POST", "/repos/tinystats/tinystats/issues/2/comments", "maintainer"),
                ("PATCH", "/repos/tinystats/tinystats/issues/2", "maintainer"),
                ("PATCH", "/repos/tinystats/tinystats/issues/4", "quest-bot"),
                ("POST", "/repos/tinystats/tinystats/issues/4/comments", "quest-bot"),
            ],
        )
        self.assertTrue(quest.is_done(self.body, "comment-on-issue"))
        quest_comment = next(
            body["body"]
            for path, body in self.post_bodies
            if path.endswith(f"/{QUEST_ISSUE}/comments")
        )
        self.assertIn("Quest XP: 1 point", quest_comment)
        self.assertIn("Badges: none yet", quest_comment)

    def test_repeated_event_does_nothing(self):
        self.run_event("issue_comment", comment_event())
        result = self.run_event("issue_comment", comment_event(number=3))
        self.assertEqual(result, "comment-on-issue: already done")
        self.assertEqual(len(self.calls), 1)

    def test_other_repository_is_ignored(self):
        payload = comment_event()
        payload["repository"]["full_name"] = "tinystats/other"
        self.assertEqual(self.run_event("issue_comment", payload), "other repository")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
