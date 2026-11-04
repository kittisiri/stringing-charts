# Stringing charts

Variable-tension stringing charts for the bench: pick a racket, mains and crosses targets (40–55 lb) and mains / crosses α, and read the dial setting for every string.

Live: https://kittisiri.github.io/stringing-charts/

## How it works

- `rackets.json` — the only hand-entered data: nine measurements per racket (cm).
- `generator/generate.py` — turns `rackets.json` into `data/<id>.json`, every scenario precomputed (2,304 per racket). Writes nothing if any check fails (fit residual, averages within ±0.2 lb, monotonic mains).
- `generator/check.py` — regression checks: derived geometry, hand-strung charts, rounding margin, byte-identical rerun, committed data up to date, grid sanity.
- `index.html` + `app.js` + `style.css` — a plain static page that only displays the data. No build step.

## Update

```
python3 generator/generate.py
python3 generator/check.py
python3 -m http.server 8000   # preview at http://localhost:8000
```

Then commit `rackets.json` and `data/*.json` together and push; GitHub Pages serves the `main` branch root.
