"""Forecast GTA VI launch-day Twitch viewers hour by hour (make.fun).

Model: comparable-launch shape forecast with a launch-size amplitude
adjustment, recalibrated in improve3 on top of the improve2 entry.
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
  - Morning-dip correction (new in improve3): the leave-one-out
    residuals of the improve2 centre are systematically negative in
    hours 3 and 4 (mean -0.15 and -0.17 log units; 9 of 10 launches
    sit below the centre at hour 4). The pool's median shape
    overstates the early-morning level: the overnight audience falls
    further after the midnight unlock wave than the median launch
    suggests, before the US unlocks lift it again. So the centre is
    lowered by 0.10 log units at hours 3 and 4 only. The correction
    is a flat plateau (depths 0.08-0.15 score within 0.0002 of each
    other on the leave-one-out protocol), so 0.10 is a central,
    untuned choice, not a sharp optimum.
  - Skewed late spread (new in improve3): from hour 6 on, the
    leave-one-out residuals are right-skewed (their mean sits above
    their median in the afternoon hours), so a symmetric band wastes
    width below the centre and starves the upper tail. The band is
    therefore asymmetric late: the lower quantiles use a log-spread
    of 0.40 and the upper quantiles 0.55, around the same centre.
    Hours 2-5 keep a symmetric 0.25 spread (their residual
    standard deviation is about 0.27). The two changes together are
    broad-based: 6 of the 10 leave-one-out launches and 3 of the 4
    practice cases improve, and they still win on a clean pool with
    the two early-access-contaminated launches removed.
  - Fallback: if fewer than 4 launches qualify, relax the filter
    (rolling launches incl. PC-global, then every launch with a full
    release day); if still none, fall back to persistence.

  - Validation (leave-one-out over the 10 qualifying comparables in
    the kit's practice cases, each launch forecast from the other 9
    only, pinball loss on the log scale): 0.2218, against 0.2245
    for the improve2 entry and 0.5812 for persistence on the same
    protocol; per-case: RE Requiem 0.5535, Hogwarts 0.1542, Yotei
    0.1946, MH Wilds 0.2610, BO6 0.1358, MWIII 0.1650, MW4 0.1767,
    Zelda 0.1356, FFVII Rebirth 0.3203, TLOU2 0.1211 (6 of 10 better
    than improve2). On the four practice cases themselves (answers
    reconstructed from SullyGnome's chart API, the same source the
    house read; validated against 926/926 history points and 4/4
    hour-1 prints in the case files): loss 0.1632, against 0.1686
    for improve2 and 0.3871 for the house baseline on the same
    reconstruction (p00 0.1855, p01 0.1269, p02 0.1186, p03 0.2219),
    typical miss 26.3%, 90% coverage 0.946, deterministic, 0.37 s
    for the 4 cases.
  - Rejected in improve3: raising the d cap to 1.5-2.0 (practice
    improves a lot, leave-one-out worsens — the cap stays 1.2);
    steepening beta to -0.65 or beyond with the dip (practice
    improves, leave-one-out worsens); a wide dip over hours 2-5
    (worse than the hours 3-4 step on both protocols); a late
    centre shift (residual means there are outlier-driven, medians
    near zero); narrowing the late spread below 0.40/0.50
    (practice improves, leave-one-out worsens).

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
DIP_DEPTH = 0.10      # morning-dip correction, log units, hours 3-4
DIP_HOURS = (3, 4)    # hours the dip correction applies to
SPREAD_EARLY = 0.25   # log-spread, hours 2-5 (LOO residual sd ~0.27)
SPREAD_LO_LATE = 0.40  # log-spread below the centre, hours 6-24
SPREAD_HI_LATE = 0.55  # log-spread above the centre, hours 6-24
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
    whole shape is then shrunk 5% toward persistence (0). Finally
    the morning-dip correction lowers hours 3 and 4 by DIP_DEPTH:
    held-out launches sit systematically below the uncorrected
    centre in those two hours, and nowhere else as consistently.
    """
    shapes = [shape for shape, _ in pool]
    firsts = [first for _, first in pool]
    base = median_shapes(shapes)
    ref = statistics.median(firsts)
    d = math.log(p1) - math.log(ref)
    d = max(-D_CAP, min(D_CAP, d))
    out = []
    for k in range(24):
        h = k + 1
        weight = math.sqrt(k / 23.0)  # k = h - 1
        value = (base[k] + BETA * weight * d) * SHRINK
        if h in DIP_HOURS:
            value -= DIP_DEPTH
        out.append(value)
    return out


def spreads(h):
    """The (lower, upper) log-spreads for hour h.

    Hours 2-5: a symmetric 0.25 band. From hour 6 the band is
    skewed: 0.40 below the centre, 0.55 above it, because the
    leave-one-out residuals are right-skewed once the unlock waves
    have hit — the day's upside is wider than its downside.
    """
    if h <= 5:
        return SPREAD_EARLY, SPREAD_EARLY
    return SPREAD_LO_LATE, SPREAD_HI_LATE


def hour_quantiles(p1, h, centre):
    """The five quantiles for hour h around hour 1's print p1."""
    middle = math.log(p1) + centre[h - 1]
    s_lo, s_hi = spreads(h)
    qs = []
    for z in Z:
        s = s_lo if z < 0 else s_hi
        qs.append(round2(math.exp(middle + z * s)))
    qs = [min(max(q, 0.01), 1_000_000_000) for q in qs]
    return sorted(qs)


def fallback_quantiles(p1, h):
    """Persistence quantiles (no qualifying pool): hour 1's print
    with the same two-sided spread the model would use."""
    s_lo, s_hi = spreads(h)
    qs = []
    for z in Z:
        s = s_lo if z < 0 else s_hi
        qs.append(round2(p1 * math.exp(z * s)))
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
            qs = fallback_quantiles(p1, h)
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
