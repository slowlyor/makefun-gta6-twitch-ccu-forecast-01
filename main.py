"""Forecast GTA VI launch-day Twitch viewers hour by hour (make.fun).

Model: comparable-launch shape forecast with a launch-size amplitude
adjustment, recalibrated in improve2.
  - Every comparable in the case is a past big launch with hourly Twitch
    viewers from 14 days before to 3 days after its release day.
  - Keep only the launches whose unlock matches GTA VI's: a rolling
    midnight-local unlock, with no simultaneous PC global unlock (a PC
    global unlock spikes hour 1 and then decays, the opposite shape).
    The GTA VI category's own pre-release history is not a launch, so
    any comparable named after Grand Theft Auto is skipped.
  - For each kept launch, take its release-day shape as the log ratio
    log(viewers_h / viewers_1) for h = 2..24 and use the per-hour
    median across launches, smoothed with a centred 3-hour moving
    average. The median shape dips a little in hours 2-5 (only
    NZ/Asia/Europe are unlocked) and rises toward the US evening as
    the US east (05:00Z) and west (08:00Z) coasts unlock and prime
    time arrives.
  - Launch-size amplitude: how far a launch's day rises above its
    hour-1 print depends on how big that print is. Small hour-1
    launches (only a thin NZ/Asia audience awake at 00:00Z) rise
    several-fold by the evening; huge hour-1 launches are already
    near their day's level and stay almost flat. So the centre is
    shifted by beta * sqrt((h - 1) / 23) * d, with beta = -0.6 and
    d = log(p1 / p_ref), p_ref the pool's median hour-1 print. The
    shift grows over the day (shapes barely differ at hour 2 and
    diverge by the evening) and is shrunk 5% toward persistence with
    the rest of the shape. d is capped at +/-1.2 log units, about the
    largest distance any pooled launch sits from the pool median, so
    a launch far bigger than anything in the pool is forecast with
    the flattest observed shape, never with a declining one.
  - Spread: a two-level log-normal band around the centre, calibrated
    on the leave-one-out residuals of this model: their standard
    deviation is about 0.27 log units in hours 2-5 and about 0.50
    from hour 6 on (the shapes diverge once the unlock waves hit and
    then stay diverged, they do not keep widening), so the band is
    0.25 for hours 2-5 and 0.50 for hours 6-24, instead of a spread
    that keeps growing as sqrt(h). A finer grid over beta (-0.55 to
    -0.65) and the two spread levels (0.22-0.28 / 0.45-0.53) is a flat
    plateau, so the chosen point is not a sharp optimum.
  - Fallback: if fewer than 4 launches qualify, relax the filter
    (rolling launches incl. PC-global, then every launch with a full
    release day); if still none, fall back to persistence.

  - Validation (leave-one-out over the 10 qualifying comparables in
    the kit's practice cases, each launch forecast from the other 9
    only, pinball loss on the log scale): 0.2245, against 0.2273 for
    the improve1 entry (beta -0.5, spread 0.30/0.55) and 0.5812 for
    persistence on the same protocol. On the four practice cases
    themselves (answers reconstructed from SullyGnome's chart API,
    the same source the house read; validated against 926/926
    history points and 4/4 hour-1 prints in the case files): loss
    0.1686, against 0.1795 for improve1 and 0.3871 for the house
    baseline on the same reconstruction, three of four practice cases
    improving (p00 0.2249 -> 0.1966, p01 0.1396 -> 0.1314,
    p02 0.1333 -> 0.1247; p03 essentially flat, 0.2202 -> 0.2218),
    typical miss 26.9%, 90% coverage 0.957, deterministic,
    0.21 s for the 4 cases.
  - Rejected in improve2: a skewed late spread (wider upper tail,
    0.45/0.55) — its LOO gain came almost entirely from one outlier
    launch (Resident Evil Requiem) while 6 of 10 LOO cases got worse;
    per-hour residual-sd spreads; empirical residual quantiles (one
    outlier inflates everyone's upper quantile); spread inflation
    with |d|; a second feature term on pre-release ratios or
    viewers-per-channel; per-hour centre bias shifts; raising the d
    cap to 1.5-2.0 (practice improves, LOO worsens — the cap stays
    1.2). A clean-pool stress test (dropping the two
    early-access-contaminated launches) favours the old parameters,
    so the gain is tied to the full tier-1 pool the entry actually
    uses; the improvement is modest and both scores move together.

Deterministic, standard library only, no network. Reads every *.in in
$MAKEFUN_INPUT_DIR (else /input) and writes <id>.out JSON to
$MAKEFUN_OUTPUT_DIR (else /output).
"""

import json
import math
import os
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]
BETA = -0.6           # size-amplitude slope, per sqrt((h-1)/23)
D_CAP = 1.2           # cap on |log(p1 / pool median p1)|
SHRINK = 0.95         # shrink the shape 5% toward persistence
SPREAD_EARLY = 0.25   # log-spread, hours 2-5 (LOO residual sd ~0.27)
SPREAD_LATE = 0.50    # log-spread, hours 6-24 (LOO residual sd ~0.50)
MIN_POOL = 4          # minimum qualifying launches before relaxing the filter


def round2(x):
    """Round to 2 decimals, half up (same convention as the starter)."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if float(value).is_integer() else value


def parse_ts(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def release_day(comp):
    """A comparable's release day as (shape, hour-1 viewers).

    shape is log(viewers_h / viewers_1) for h = 1..24. Returns None
    when the comparable has no complete release day or its hour-1
    count is not positive.
    """
    try:
        day_start = parse_ts(comp["day_start"])
    except (KeyError, TypeError, ValueError):
        return None
    hours = {}
    for row in comp.get("hourly") or []:
        try:
            when = parse_ts(row["from"])
            viewers = row["viewers"]
        except (KeyError, TypeError, ValueError):
            continue
        h = int((when - day_start).total_seconds() // 3600) + 1
        if 1 <= h <= 24 and isinstance(viewers, (int, float)):
            hours[h] = viewers
    if len(hours) != 24 or not hours[1] or hours[1] <= 0:
        return None
    first = max(1.0, float(hours[1]))
    shape = [math.log(max(1.0, float(hours[h])) / first) for h in range(1, 25)]
    return shape, first


def unlock_kind(comp):
    """Classify a comparable's unlock from its research note.

    Returns "rolling" (midnight local, rolling), "rolling_pc" (rolling
    consoles plus a simultaneous PC global unlock), or "other".
    """
    note = (comp.get("unlock") or "").lower()
    rolling = "midnight local" in note or "rolling" in note
    pc_global = "pc" in note and ("global" in note or "simultaneous" in note)
    if rolling and pc_global:
        return "rolling_pc"
    if rolling:
        return "rolling"
    return "other"


def collect_pool(case):
    """The qualifying launches as a list of (shape, hour-1 viewers).

    Tier 1: rolling midnight-local launches without a PC global unlock
    (GTA VI's own unlock type, console-only). Tier 2 adds the PC-global
    rolling launches. Tier 3 is every launch with a full release day.
    """
    tiers = {"rolling": [], "rolling_pc": [], "other": []}
    for comp in sorted(case.get("comparables") or [], key=lambda c: c.get("name", "")):
        if "grand theft auto" in (comp.get("name") or "").lower():
            continue  # the category's own pre-release history, not a launch
        entry = release_day(comp)
        if entry is None:
            continue
        tiers[unlock_kind(comp)].append(entry)
    for wanted in (["rolling"],
                   ["rolling", "rolling_pc"],
                   ["rolling", "rolling_pc", "other"]):
        pool = [e for kind in wanted for e in tiers[kind]]
        if len(pool) >= MIN_POOL:
            return pool
    return [e for kind in ("rolling", "rolling_pc", "other") for e in tiers[kind]]


def median_shapes(shapes):
    """Per-hour median log-ratio shape, lightly smoothed.

    A centred 3-hour moving average: launch-day shapes move smoothly
    (unlock waves, then prime time), and the per-hour median over ~10
    launches is noisy hour to hour.
    """
    raw = [statistics.median(s[h] for s in shapes) for h in range(24)]
    out = []
    for k in range(24):
        lo = max(0, k - 1)
        hi = min(24, k + 2)
        out.append(statistics.mean(raw[lo:hi]))
    return out


def centre_shape(pool, p1):
    """The forecast centre (log ratio to hour 1) for each hour 1..24.

    The pool's median shape, shifted by the launch-size amplitude:
    a launch whose hour-1 print sits above the pool's median print
    is forecast flatter, one below it steeper, by BETA *
    sqrt((h - 1) / 23) * d, where d is the capped log distance of
    this launch's hour-1 print from the pool's median print. The
    whole shape is then shrunk 5% toward persistence (0).
    """
    shapes = [shape for shape, _ in pool]
    firsts = [first for _, first in pool]
    base = median_shapes(shapes)
    ref = statistics.median(firsts)
    d = math.log(p1) - math.log(ref)
    d = max(-D_CAP, min(D_CAP, d))
    out = []
    for k in range(24):
        weight = math.sqrt(k / 23.0)  # k = h - 1
        out.append((base[k] + BETA * weight * d) * SHRINK)
    return out


def spread(h):
    """The log-spread for hour h: 0.25 in hours 2-5, 0.50 from hour 6."""
    return SPREAD_EARLY if h <= 5 else SPREAD_LATE


def hour_quantiles(p1, h, centre):
    """The five quantiles for hour h around hour 1's print p1."""
    middle = math.log(p1) + centre[h - 1]
    s = spread(h)
    qs = [round2(math.exp(middle + z * s)) for z in Z]
    qs = [min(max(q, 0.01), 1_000_000_000) for q in qs]
    return sorted(qs)


def forecast_case(case, name):
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1.0, float(first["viewers"]))

    pool = collect_pool(case)
    centre = centre_shape(pool, p1) if pool else None
    rows = []
    for row in case["forecast"]:
        h = row["hour"]
        if centre is not None:
            qs = hour_quantiles(p1, h, centre)
        else:
            qs = [round2(p1 * math.exp(z * spread(h))) for z in Z]
            qs = [min(max(q, 0.01), 1_000_000_000) for q in qs]
            qs = sorted(qs)
        rows.append({"hour": h, "q": qs})
    return {"hours": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
