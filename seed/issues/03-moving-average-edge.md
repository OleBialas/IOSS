---
title: "moving_average() drops the last window"
labels: [bug]
opened_by: fellow contributor
patch: 03-moving-average-edge.patch
difficulty: 3
---

`moving_average()` returns one value too few:

```python
>>> from tinystats import moving_average
>>> moving_average([1, 2, 3, 4, 5], 3)
[2.0, 3.0]
>>> moving_average([1, 2, 3], 3)
[]
```

I expected `[2.0, 3.0, 4.0]` and `[2.0]`. The docstring says the function returns `len(x) - window + 1` values.

The tests pass, so they do not catch this.
