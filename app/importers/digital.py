"""Streaming digital VCD and wide CSV import. Retain only the selected interval."""

import csv
import re
from collections import defaultdict
from decimal import Decimal
from app.core.model import Project, Track, Edge, COLORS, ticks


def finish(tracks, end, name):
    if not tracks:
        raise ValueError("没有可导入的数字信号 / No digital signals")
    for i, s in enumerate(tracks):
        s.color = COLORS[i % len(COLORS)]
        es = s.edges
        if (
            s.kind == "signal"
            and len(es) >= 5
            and all(e.value in ("0", "1") for e in es)
        ):
            period = es[2].t
            high = es[1].t
            if (
                period
                and high * 100 % period == 0
                and all(
                    e.t == (j // 2) * period + (high if j % 2 else 0)
                    and e.value == es[j % 2].value
                    for j, e in enumerate(es)
                )
                and es[0].value != es[1].value
            ):
                next_t = (len(es) // 2) * period + (high if len(es) % 2 else 0)
                if next_t >= end:
                    s.kind, s.period, s.duty, s.start_high = (
                        "clock",
                        period,
                        (high if es[0].value == "1" else period - high) * 100 // period,
                        es[0].value == "1",
                    )
                    s.edges = [es[0]]
    p = Project(name=name, duration=end, step=max(1, end // 24), tracks=tracks)
    p.validate()
    return p


def record(s, t, v):
    if s.edges[-1].t == t:
        s.edges[-1].value = v
    elif s.edges[-1].value != v:
        s.edges.append(Edge(t, v))


def read_vcd(path, lo=0, hi=10**15 - 1):
    tracks = []
    symbols = defaultdict(list)
    scale = 1
    time = 0
    scope = []
    with open(path, encoding="utf-8-sig") as f:
        words = (word for line in f for word in line.split())
        for word in words:
            if word in ("$dumpvars", "$dumpall", "$dumpon", "$dumpoff", "$end"):
                continue
            if word.startswith("$"):
                args = []
                for v in words:
                    if v == "$end":
                        break
                    args.append(v)
                if word == "$timescale":
                    m = re.fullmatch(r"(\d+)(fs|ps|ns|us|ms|s)", "".join(args))
                    if not m:
                        raise ValueError("Invalid VCD timescale")
                    scale = (
                        Decimal(m[1])
                        * {
                            "fs": Decimal(".001"),
                            "ps": 1,
                            "ns": 1000,
                            "us": 10**6,
                            "ms": 10**9,
                            "s": 10**12,
                        }[m[2]]
                    )
                elif word == "$scope":
                    scope.append(args[1])
                elif word == "$upscope":
                    scope.pop()
                elif word == "$var" and args[0] not in (
                    "real",
                    "realtime",
                    "string",
                    "event",
                ):
                    width = int(args[1])
                    s = Track(
                        args[3],
                        "signal" if width == 1 else "bus",
                        width=width,
                        group=".".join(scope),
                        edges=[Edge(0, "X")],
                    )
                    tracks.append(s)
                    symbols[args[2]].append(s)
            elif word.startswith("#"):
                n = int(word[1:]) * scale
                if n != int(n) or n < time:
                    raise ValueError(
                        "时间超出 1 ps 精度或未排序 / Invalid VCD timestamp"
                    )
                time = int(n)
                if time > hi:
                    break
            else:
                v = word[0].lower()
                if v in "brs":
                    sym = next(words)
                    if v != "b":
                        continue
                    bits = word[1:].upper()
                    val = (
                        "X"
                        if "X" in bits
                        else (
                            "Z"
                            if set(bits) == {"Z"}
                            else "X" if "Z" in bits else str(int(bits, 2))
                        )
                    )
                elif v in "01xz":
                    sym, val = word[1:], v.upper()
                else:
                    continue
                for s in symbols[sym]:
                    record(s, max(0, time - lo), val)
    if time < lo:
        raise ValueError("裁剪范围为空 / Empty crop")
    return finish(tracks, min(time, hi) - lo + 1, path.stem)


def read_csv(path, lo=0, hi=10**15 - 1):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        head = next(reader)
        unit = head[0].strip().lower().replace("us", "μs").removeprefix("time_")
        if unit == "time":
            unit = "ns"
        tracks = []
        for label in head[1:]:
            m = re.fullmatch(r"(.+?)(?:\[(\d+)(?::0)?\])?", label.strip())
            if not m:
                raise ValueError("Invalid CSV column")
            width = int(m[2]) + (1 if ":0]" in label else 0) if m[2] else 1
            tracks.append(
                Track(
                    m[1],
                    "bus" if width > 1 else "signal",
                    width=width,
                    radix=10,
                    edges=[Edge(0, "X")],
                )
            )
        last = -1
        for row in reader:
            t = ticks(row[0], unit)
            if t < last:
                raise ValueError("CSV 时间未排序 / Unsorted CSV")
            last = t
            if t > hi:
                break
            for s, v in zip(tracks, row[1:], strict=True):
                record(s, max(0, t - lo), s.normalize(v))
        if last < lo:
            raise ValueError("Empty crop")
    return finish(tracks, min(hi, last) - lo + 1, path.stem)
