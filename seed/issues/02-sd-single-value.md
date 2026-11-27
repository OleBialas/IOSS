---
title: "sd() crashes with ZeroDivisionError for one value"
labels: [bug, good first issue]
opened_by: fellow contributor
patch: 02-sd-single-value.patch
difficulty: 2
---

`sd()` crashes when I give it one value:

```python
>>> from tinystats import sd
>>> sd([5])
ZeroDivisionError: division by zero
```

The docstring says that `sd()` raises a `ValueError` for fewer than two values. I expected that error with a clear message.

`sd([])` also gives a confusing message about "at least one value".
