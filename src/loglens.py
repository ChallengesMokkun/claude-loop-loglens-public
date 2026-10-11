#!/usr/bin/env python3
"""Aggregate ERROR/WARN/INFO counts from log files (plain text or JSON Lines).

Usage:
    python loglens.py count app.log
    python loglens.py count app.log --level ERROR
    python loglens.py count app.log --since 09:00:00 --until 17:30:00
    python loglens.py count app.jsonl
    python loglens.py count a.log b.jsonl
    python loglens.py count app.log --top 3
    python loglens.py count app.log --format json
    python loglens.py count app.log --format csv
    python loglens.py count app.log --regex "timeout|refused"
    python loglens.py count app.log --stats

When several files are given, their counts are summed into a single
report in the same format as for one file (no per-file breakdown).
.log and .jsonl files may be mixed; the format is chosen per file, and
--level/--since/--until apply to every file.

Files with a .jsonl extension are read as JSON Lines: one JSON object
per line with "timestamp" ("YYYY-MM-DD HH:MM:SS"), "level"
(ERROR/WARN/INFO), and "message" keys. Lines that are not valid JSON,
are missing a required key, or have a level outside ERROR/WARN/INFO
are counted as OTHER (subject to the same --since/--until exclusion
rule as unmatched text lines).

--top N prints the N most frequent messages after the level counts,
one per line as "COUNT MESSAGE". Ties keep the order in which the
messages first appear. Only lines left after --level/--since/--until
filtering are counted, and OTHER lines are never included.

--format json prints the same result as one JSON object instead:
{"counts": {...}, "total": N}, plus a "top" list of
{"count": N, "message": "..."} when --top is given. With --level,
"counts" holds only that level and "total" is its count.

--format csv prints a "level,count" header followed by one row per
level (ERROR, WARN, INFO, OTHER) and a TOTAL row. With --top, a blank
line and a "count,message" section follow. Messages are quoted with
the standard CSV rules. With --level, only that level and TOTAL rows
are printed.

--regex PATTERN keeps only lines whose message matches the Python
regular expression PATTERN (re.search, case-sensitive). It is applied
together with every other filter; OTHER lines have no message, so they
are excluded whenever --regex is given. An invalid pattern prints the
pattern and the reason to stderr and exits with status 2.

--stats prints a blank line after the normal counts, followed by one
"HH時 N件" line per hour (00-23) that has at least one matching line,
in time order. It applies after every other filter (--level/--since/
--until/--regex); OTHER lines have no timestamp, so they are never
counted. With --format json, the same breakdown is added as a "stats"
key ({"HH": N}, only the hours that occur, time order) at the end of
the object. --stats is not supported with --format csv: it prints an
error to stderr and exits with status 2.

--output PATH writes the report (in whichever --format was chosen)
to PATH instead of stdout, and prints "wrote: PATH" to stdout instead.
The file is written as UTF-8 and always ends with a newline; an
existing file at PATH is overwritten. If PATH's parent directory does
not exist, an "error:" message is printed to stderr and the command
exits with status 2.
"""
import argparse
import csv
import io
import json
import os
import re
import sys
from collections import Counter

LOG_LINE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s+(\d{2}:\d{2}:\d{2})\s+(ERROR|WARN|INFO)\b\s*(.*)$"
)

JSONL_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s+(\d{2}:\d{2}:\d{2})$")

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d:[0-5]\d$")

LEVELS = ["ERROR", "WARN", "INFO", "OTHER"]


def parse_text_line(line):
    match = LOG_LINE_RE.match(line)
    if match:
        return match.groups()
    return None


def parse_jsonl_line(line):
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    timestamp = obj.get("timestamp")
    level = obj.get("level")
    message = obj.get("message")
    if not isinstance(timestamp, str) or not isinstance(message, str):
        return None
    if level not in ("ERROR", "WARN", "INFO"):
        return None
    match = JSONL_TIMESTAMP_RE.match(timestamp)
    if not match:
        return None
    return match.group(1), level, message


def parse_time(value):
    if not TIME_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"invalid time: {value!r} (expected HH:MM:SS)"
        )
    return value


def parse_positive_int(value):
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number < 1:
        raise argparse.ArgumentTypeError(
            f"invalid count: {value!r} (expected a positive integer)"
        )
    return number


def iter_records(path, since=None, until=None, pattern=None):
    """Yield (time, level, message) for each non-empty line kept by the filters.

    OTHER lines are yielded as (None, "OTHER", None).
    """
    # HH:MM:SS is zero-padded, so string comparison matches time order.
    filtering = since is not None or until is not None or pattern is not None
    parse_line = parse_jsonl_line if path.endswith(".jsonl") else parse_text_line
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parsed = parse_line(line)
            if parsed:
                time, level, message = parsed
                if since is not None and time < since:
                    continue
                if until is not None and time > until:
                    continue
                if pattern is not None and not pattern.search(message):
                    continue
                yield time, level, message
            elif not filtering:
                # OTHER lines have no timestamp or message, so they are
                # excluded whenever a time range or pattern is given.
                yield None, "OTHER", None


def count_log_levels(path, since=None, until=None, pattern=None):
    return Counter(
        level for _, level, _ in iter_records(path, since, until, pattern)
    )


def count_files(paths, since=None, until=None, pattern=None):
    # Each file's format is chosen by its own extension.
    counts = Counter()
    for path in paths:
        counts.update(
            count_log_levels(path, since=since, until=until, pattern=pattern)
        )
    return counts


def count_messages(paths, since=None, until=None, level=None, pattern=None):
    # Counter keeps insertion order, and most_common() sorts stably, so
    # messages with equal counts stay in order of first appearance.
    messages = Counter()
    for path in paths:
        for _, line_level, message in iter_records(path, since, until, pattern):
            if line_level == "OTHER":
                continue
            if level is not None and line_level != level:
                continue
            messages[message] += 1
    return messages


def count_hourly(paths, since=None, until=None, level=None, pattern=None):
    # OTHER lines have no timestamp, so they never contribute an hour.
    hours = Counter()
    for path in paths:
        for time, line_level, _ in iter_records(path, since, until, pattern):
            if time is None:
                continue
            if level is not None and line_level != level:
                continue
            hours[time[:2]] += 1
    return hours


def cmd_count(args):
    paths = [args.logfile] + list(getattr(args, "more_logfiles", None) or [])
    since = getattr(args, "since", None)
    until = getattr(args, "until", None)
    level = getattr(args, "level", None)
    top = getattr(args, "top", None)
    regex = getattr(args, "regex", None)
    stats = getattr(args, "stats", False)
    if stats and getattr(args, "format", "text") == "csv":
        print("Error: --stats is not supported with --format csv", file=sys.stderr)
        return 2
    pattern = None
    if regex is not None:
        try:
            pattern = re.compile(regex)
        except re.error as e:
            print(f"Error: invalid regex {regex!r}: {e}", file=sys.stderr)
            return 2
    try:
        counts = count_files(paths, since=since, until=until, pattern=pattern)
        if top:
            messages = count_messages(
                paths, since=since, until=until, level=level, pattern=pattern
            )
        if stats:
            hourly = count_hourly(
                paths, since=since, until=until, level=level, pattern=pattern
            )
    except FileNotFoundError as e:
        print(f"Error: file not found: {e.filename}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Error: could not read {e.filename}: {e}", file=sys.stderr)
        return 1

    output_path = getattr(args, "output", None)
    if output_path is not None:
        parent = os.path.dirname(output_path)
        if parent and not os.path.isdir(parent):
            print(f"error: parent directory does not exist: {parent}", file=sys.stderr)
            return 2

    buffer = io.StringIO()
    out = buffer if output_path is not None else sys.stdout

    if getattr(args, "format", "text") == "json":
        names = [level] if level else LEVELS
        result = {
            "counts": {name: counts.get(name, 0) for name in names},
            "total": sum(counts.get(name, 0) for name in names),
        }
        if top:
            result["top"] = [
                {"count": count, "message": message}
                for message, count in messages.most_common(top)
            ]
        if stats:
            result["stats"] = {hour: hourly[hour] for hour in sorted(hourly)}
        print(json.dumps(result, indent=2, ensure_ascii=False), file=out)
    elif getattr(args, "format", "text") == "csv":
        names = [level] if level else LEVELS
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["level", "count"])
        for name in names:
            writer.writerow([name, counts.get(name, 0)])
        writer.writerow(["TOTAL", sum(counts.get(name, 0) for name in names)])
        if top:
            writer.writerow([])
            writer.writerow(["count", "message"])
            for message, count in messages.most_common(top):
                writer.writerow([count, message])
    else:
        if level:
            print(f"{level} {counts.get(level, 0)}", file=out)
        else:
            total = sum(counts.values())
            width = max(len(name) for name in LEVELS + ["TOTAL"])
            for name in LEVELS:
                print(f"{name:<{width}} : {counts.get(name, 0)}", file=out)
            print(f"{'TOTAL':<{width}} : {total}", file=out)

        if top:
            for message, count in messages.most_common(top):
                print(f"{count} {message}", file=out)

        if stats:
            print(file=out)
            for hour in sorted(hourly):
                print(f"{hour}時 {hourly[hour]}件", file=out)

    if output_path is not None:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(buffer.getvalue())
        print(f"wrote: {output_path}")

    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="loglens.py",
        description="Aggregate ERROR/WARN/INFO counts from a log file.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    count_parser = subparsers.add_parser(
        "count", help="Count log lines by level (ERROR/WARN/INFO)"
    )
    count_parser.add_argument("logfile", help="Path to the log file")
    count_parser.add_argument(
        "more_logfiles",
        nargs="*",
        metavar="logfile",
        help="Additional log files; counts are summed across all files",
    )
    count_parser.add_argument(
        "--level",
        choices=LEVELS,
        help="Show only the count for this level (ERROR/WARN/INFO/OTHER)",
    )
    count_parser.add_argument(
        "--since",
        type=parse_time,
        help="Count only lines at or after this time (HH:MM:SS)",
    )
    count_parser.add_argument(
        "--until",
        type=parse_time,
        help="Count only lines at or before this time (HH:MM:SS)",
    )
    count_parser.add_argument(
        "--top",
        type=parse_positive_int,
        metavar="N",
        help="Also show the N most frequent messages (OTHER lines excluded)",
    )
    count_parser.add_argument(
        "--format",
        choices=["text", "json", "csv"],
        default="text",
        help="Output format (default: text)",
    )
    count_parser.add_argument(
        "--regex",
        metavar="PATTERN",
        help="Count only lines whose message matches this Python regex",
    )
    count_parser.add_argument(
        "--stats",
        action="store_true",
        help="Also show an hourly breakdown of matching lines (not with --format csv)",
    )
    count_parser.add_argument(
        "--output",
        metavar="PATH",
        help="Write the report to PATH instead of stdout",
    )
    count_parser.set_defaults(func=cmd_count)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
