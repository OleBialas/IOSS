# Seed data

The seed data turns a clean copy of [tinystats](https://github.com/florence-bockting/tinystats) into the practice repository of a scenario.

- `patches/`: the planted bugs. Apply them in number order. Each patch expects the earlier patches.
- `issues/`: the issue texts. Load them into the mock issue tracker. The front matter names the patch that causes each issue.

After all patches, the tests and `ruff` still pass. The learner must find the bugs from the issues, not from a red CI.

Apply the patches to a clean clone. Run this command in the clone:

```bash
git apply /path/to/IOSS/seed/patches/*.patch
```
