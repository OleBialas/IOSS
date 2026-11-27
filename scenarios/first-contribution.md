# Scenario: a newcomer's first contribution

> Draft. The format is Markdown until the structure is stable. Then we convert it to YAML.

| Field | Value |
| :-- | :-- |
| Repository | [tinystats](https://github.com/florence-bockting/tinystats), with the patches in [`seed/patches/`](../seed/patches/) |
| Issues | [`seed/issues/`](../seed/issues/) |
| Player | Newcomer |
| Duration | About 2 hours |
| Prerequisites | A GitHub account. No local install for the Codespaces path. |

## Learning goals

| ID | Goal |
| :-- | :-- |
| G1 | Set up the environment |
| G2 | Understand the project structure |
| G3 | Make a change following the contribution guidelines |
| G4 | Respond to review |

## Roles

| Role | Played by | LLM style (when an LLM plays the role) |
| :-- | :-- | :-- |
| Newcomer | The player | — |
| Fellow contributor | Peer, else LLM | Helpful. Answers questions. Does not write the fix. |
| Maintainer | Peer, else LLM | Friendly and short. Assigns issues. Merges. |
| Reviewer | Peer, else LLM | Set per session: helpful, terse or picky. |
| CI bot | Script | Runs the workflow in `.github/workflows/ci.yml`. |

## Interaction rules

1. A peer fills each role first. An LLM fills a role only when no peer is available.
2. Mark each message from an LLM as an LLM message.
3. The LLM can explain or help to draft. It never gives the notebook feedback that counts. Only peers and mentors give that feedback.
4. The LLM never writes the fix for the player.

## Steps

Each step names its learning goal, the player action, the actor actions, the completion condition and the notebook prompt.

### Step 0: set up the environment (G1)

- **Player:** open the repository in a Codespace or a local Dev Container. Run `uv run pytest`.
- **Actors:** the fellow contributor answers setup questions.
- **Done when:** the output shows `13 passed`.
- **Notebook prompt:** *What went wrong during setup? How did you solve it?*

### Step 1: explore the project (G2)

- **Player:** answer three questions in the notebook:
  1. In which file is `mean()` defined?
  2. Which file sets the pytest options?
  3. Which checks does CI run on a pull request?
- **Actors:** none.
- **Done when:** the notebook has the three answers. The answers are `src/tinystats/core.py`, `pyproject.toml`, and `ruff check`, `ruff format --check` and `pytest`.
- **Notebook prompt:** *Describe the project structure in your own words. What was hard to find?*

### Step 2: choose an issue (G3)

- **Player:** read the open issues. Choose one. Write a comment that you want to work on it.
- **Actors:** the maintainer assigns the issue to the player. The maintainer points to `CONTRIBUTING.md`.
- **Done when:** the issue has the player as assignee.
- **Notebook prompt:** *Why did you choose this issue? What do you expect to be difficult?*

### Step 3: make the change (G3)

- **Player:** create a branch. Fix the issue. Add a test when the behaviour changes. Add a line to `CHANGELOG.md`.
- **Actors:** the fellow contributor answers questions.
- **Done when:** `uv run pytest`, `uv run ruff check` and `uv run ruff format --check` pass locally.
- **Notebook prompt:** *Which rule in `CONTRIBUTING.md` was new to you?*

### Step 4: open a pull request (G3)

- **Player:** push the branch. Open a pull request with `Closes #<number>` in the description.
- **Actors:** the CI bot runs the checks. The CI bot writes the result on the pull request.
- **Done when:** all CI checks pass.
- **Notebook prompt:** *How did you describe your change? What does the reviewer need to know?*

### Step 5: receive review (G4)

- **Player:** read each review comment. Answer each comment.
- **Actors:** the reviewer writes the review comments for the issue. See [Review comments](#review-comments).
- **Done when:** the player answered each comment.
- **Notebook prompt:** *What was unclear in the feedback you received?*

### Step 6: revise (G4)

- **Player:** push one commit for each requested change.
- **Actors:** the CI bot runs the checks again. The reviewer approves when all requested changes are done.
- **Done when:** the pull request has an approval and the CI checks pass.
- **Notebook prompt:** *Which comment changed your solution the most?*

### Step 7: merge and reflect (G1–G4)

- **Player:** write the final reflection.
- **Actors:** the maintainer merges the pull request. A peer or mentor comments on the reflection.
- **Done when:** the pull request is merged and the reflection has a human comment.
- **Notebook prompt:** *What would you do differently in your next contribution?*

## Issues and expected solutions

The clean `main` of tinystats is the correct solution for all three issues.

| Issue | Difficulty | Expected fix |
| :-- | :-- | :-- |
| [01 README example fails](../seed/issues/01-readme-typo.md) | 1 | Change `moving_avarage` to `moving_average` in both lines of the README example. |
| [02 `sd()` crashes for one value](../seed/issues/02-sd-single-value.md) | 2 | Raise `ValueError` when `len(x) < 2`. Add a test for `[]` and `[1]`. |
| [03 `moving_average()` drops the last window](../seed/issues/03-moving-average-edge.md) | 3 | Use `range(len(x) - window + 1)`. Test all values, including `window == len(x)`. Restore the doctest. |

## Review comments

The reviewer uses these comments when the player's pull request has the problem. The reviewer adds comments when a peer sees other problems.

**All issues:**

- No line in `CHANGELOG.md`: *Please add a line under `Unreleased` in `CHANGELOG.md`.*
- No `Closes #<number>`: *Please link the issue in the description.*

**Issue 01:**

- Only one of the two lines is fixed: *The function name is also wrong in the line below. Can you fix both?*

**Issue 02:**

- No test: *Please add a test that checks the `ValueError`.*
- Test only for `[1]`: *Please also test the empty list.*
- New message differs from the docstring: *The docstring says "fewer than two values". Please use the same words in the error.*

**Issue 03:**

- The test checks only the length: *Please compare all values with `pytest.approx`.*
- No test for `window == len(x)`: *This is the edge case from the issue. Please add a test for it.*
- No doctest: *An example in the docstring helps users. Can you add one?*

## Open questions

- How long does the LLM wait for a peer before it fills a role?
- Does the player choose the reviewer style, or does the mentor choose it?
- Do several players share one sandbox, each with a different issue?
