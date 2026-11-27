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

1. Creates the admin `ioss-admin` and the actors `maintainer`, `reviewer`, `newcomer`, `fellow` and `ci-bot`.
2. Creates the repository `tinystats/tinystats`.
3. Applies the [seed patches](../seed/patches/) to a clean tinystats. Pushes the result as one commit.
4. Creates the labels and the 3 [issues](../seed/issues/). The user `fellow` opens the issues.
5. Writes the test passwords and the admin token to `.env`. Git ignores this file.
6. Registers the CI runner for the organisation `tinystats`.

When `.env` exists, the script skips steps 1–5. It does step 6 only if the runner has no config yet.

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

- Scripted and LLM actors that comment and review
