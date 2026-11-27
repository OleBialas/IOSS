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

To use a local copy of tinystats, run `python3 setup.py --source /path/to/tinystats`.

## Use

Open <http://localhost:3000/tinystats/tinystats>. Log in as `newcomer` with the password from `.env`.

Clone the repository:

```bash
git clone http://localhost:3000/tinystats/tinystats.git
```

The port binds to `127.0.0.1`. Other machines cannot reach the sandbox.

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

- CI: a Forgejo runner that runs `.github/workflows/ci.yml`
- Scripted and LLM actors that comment and review
