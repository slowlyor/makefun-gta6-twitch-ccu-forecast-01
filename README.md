# makefun-gta6-twitch-ccu-forecast-01

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/slowlyor/makefun-gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/slowlyor/makefun-gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

A comparable-launch shape forecaster: it predicts GTA VI's hourly Twitch viewers from its hour-1 print using the median release-day shape of past rolling-midnight console launches, shifted by a launch-size amplitude effect (bigger hour-1 print → flatter day, slope −0.6 per √((h−1)/23) of the capped log distance from the pool median), with a −0.10 log-unit correction at hours 3–4 where held-out launches sit systematically below the median shape, and a skewed late spread (0.40 below / 0.55 above the centre from hour 6, 0.25 symmetric in hours 2–5) calibrated on leave-one-out residuals.

## Validation

- Leave-one-out over the 10 qualifying comparables: pinball loss **0.2218** (improve2: 0.2245; persistence: 0.5812).
- Practice cases p00–p03: loss **0.1632** (improve2: 0.1686; house baseline: 0.3871), typical miss 26.3%, 90% coverage 0.946, deterministic, 0.37 s for the 4 cases.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=vxw5vmyv&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
