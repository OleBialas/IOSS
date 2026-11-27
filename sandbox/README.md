# Sandbox

A local [Forgejo](https://forgejo.org/) instance for the [first-contribution scenario](../scenarios/first-contribution.md). Nothing reaches GitHub.

## Requirements

- Docker with `docker compose`
- Python 3.11 or later
- Git

## Start

Start Forgejo:

```bash
docker compose up -d
```

Populate it:

```bash
python3 setup.py
```

The script does these steps:

1. Creates the admin `ioss-admin` and the actors `maintainer`, `reviewer`, `newcomer`, `fellow`, `ci-bot` and `quest-bot`.
2. Creates the repository `tinystats/tinystats`.
3. Applies the [seed patches](../seed/patches/) to a clean tinystats. Pushes the result as one commit.
4. Creates the labels and the 3 [issues](../seed/issues/). The user `fellow` opens the issues.
5. Creates the webhook to the game master and the quest issue. See [Quests](#quests).
6. Writes the test passwords, the admin token and the webhook secret to `.env`. Git ignores this file. Starts the game master again, so it reads `.env`.
7. Registers the CI runner for the organisation `tinystats`.

When `.env` exists, the script skips steps 1–6. It does step 7 only if the runner has no config yet.

To use a local copy of tinystats, run `python3 setup.py --source /path/to/tinystats`.

## Use

Open <http://localhost:3000/tinystats/tinystats>. Log in as `newcomer` with the password from `.env`.

Clone the repository:

```bash
git clone http://localhost:3000/tinystats/tinystats.git
```

The port binds to `127.0.0.1`. Other machines cannot reach the sandbox.

## CI

Each push and each pull request runs `.github/workflows/ci.yml` of tinystats. Open **Actions** in the repository to see the results.

- `runner`: the Forgejo runner. The label `ubuntu-latest` uses the image `node:24-bookworm`.
- `dind`: the Docker daemon for the jobs. It shares the network of `forgejo`, so a job reaches Forgejo at `localhost:3000`.
- `DEFAULT_ACTIONS_URL` is `https://github.com`, because `data.forgejo.org` does not mirror `astral-sh/setup-uv`.

**Warning:** `dind` runs as a privileged container. Do not run the sandbox on a machine where this is not allowed.

The first job takes about 5 minutes, because `dind` downloads the images. Later jobs take less than 1 minute. CI needs internet access to download `uv`, Python and the actions.

## Repository tour

A guided tour shows the newcomer the files of the repository: README, LICENSE, CONTRIBUTING and the others. It uses [Driver.js](https://driverjs.com) 1.14.0 (MIT).

- The tour starts by itself on the first visit to the home page of a repository. The browser remembers this in `localStorage`.
- The **Start tour** button at the bottom right starts it again.
- The tour skips a step when the page has no matching element.

| File | Content |
| :-- | :-- |
| [`tour/assets/steps.js`](tour/assets/steps.js) | The text of each step. Edit the tour here. |
| [`tour/assets/tour.js`](tour/assets/tour.js) | Starts the tour and adds the button. |
| [`tour/footer.tmpl`](tour/footer.tmpl) | Loads the scripts on each Forgejo page. |
| [`tour/assets/vendor/`](tour/assets/vendor/) | Driver.js and its license. No CDN is needed. |

`compose.yaml` mounts these files into the Forgejo custom folder `/data/gitea`. After a change in `steps.js`, reload the page. After a change in `footer.tmpl`, restart Forgejo:

```bash
docker compose restart forgejo
```

**Warning:** Forgejo does not support template overrides. A Forgejo upgrade can break `footer.tmpl` or the CSS selectors in `steps.js`. Test the tour after each upgrade.

## Quests

A pinned quest issue gives the newcomer the tasks of the scenario as a checklist. The game master ticks the boxes.

1. The newcomer does a task, for example a comment on an issue.
2. Forgejo sends the event to the game master with a webhook.
3. The game master finds the task that the event completes.
4. An actor replies in the game world. For example, `maintainer` thanks the newcomer and assigns the issue.
5. `quest-bot` ticks the box in the quest issue. Then it names the next task.

The game master ignores events from all users except the player. A ticked box stops a second reply for the same task.

| File | Content |
| :-- | :-- |
| [`game-master/quests.toml`](game-master/quests.toml) | The tasks and the replies. Edit the quest here. |
| [`game-master/quest.py`](game-master/quest.py) | The checklist and the match of events to tasks. `setup.py` uses it too. |
| [`game-master/server.py`](game-master/server.py) | The webhook service. |
| [`game-master/test_game_master.py`](game-master/test_game_master.py) | The unit tests. |

To add a task, add a `[[task]]` block to `quests.toml`. The comment at the top of the file explains the fields. The game master reads the file for each event, so no restart is necessary.

**Warning:** `setup.py` writes the checklist only once. A new task shows in the quest issue only after a reset.

A task can use the events `issue_comment` and `pull_request`. For a new event type, add it to `target()` in `quest.py` and to the webhook events in `setup.py`.

Run the unit tests:

```bash
cd game-master && python3 -m unittest
```

Read the log of the game master:

```bash
docker compose logs game-master
```

Forgejo also shows each delivery and the response at <http://localhost:3000/org/tinystats/settings/hooks>. Log in as `ioss-admin`.

## Reset

**Warning:** this deletes all users, issues and pull requests of the sandbox.

```bash
docker compose down -v
```

```bash
rm .env
```

Then start again.

## Not done yet

- Scripted and LLM actors that review. The game master replies with fixed text only.
- Tasks for the review, the revision and the merge (Steps 5–7)
- Points and badges
