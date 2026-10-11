import argparse
import json
from pathlib import Path

import pytest

import loglens


def write_log(tmp_path, lines):
    path = tmp_path / "test.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def write_jsonl_log(tmp_path, lines):
    path = tmp_path / "test.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def test_counts_error_warn_info(tmp_path):
    logfile = write_log(
        tmp_path,
        [
            "2026-07-18 09:12:03 INFO Server started on port 8080",
            "2026-07-18 09:12:05 WARN Disk usage high",
            "2026-07-18 09:12:10 ERROR Failed to connect to database",
            "2026-07-18 09:12:15 INFO Request handled",
            "2026-07-18 09:12:20 ERROR Timeout occurred",
        ],
    )

    counts = loglens.count_log_levels(logfile)

    assert counts["ERROR"] == 2
    assert counts["WARN"] == 1
    assert counts["INFO"] == 2
    assert counts.get("OTHER", 0) == 0


def test_counts_other_for_unmatched_lines(tmp_path):
    logfile = write_log(
        tmp_path,
        [
            "2026-07-18 09:12:03 INFO Server started on port 8080",
            "Traceback (most recent call last):",
            '  File "app.py", line 10, in <module>',
            '    raise ValueError("boom")',
            "ValueError: boom",
            "2026-07-18 09:12:20 ERROR Timeout occurred",
        ],
    )

    counts = loglens.count_log_levels(logfile)

    assert counts["INFO"] == 1
    assert counts["ERROR"] == 1
    assert counts["OTHER"] == 4


def test_total_matches_non_empty_line_count(tmp_path):
    lines = [
        "2026-07-18 09:12:03 INFO Server started on port 8080",
        "2026-07-18 09:12:05 WARN Disk usage high",
        "2026-07-18 09:12:10 ERROR Failed to connect to database",
        "not a log line",
        "",
        "2026-07-18 09:12:15 INFO Request handled",
        "",
        "2026-07-18 09:12:20 ERROR Timeout occurred",
    ]
    logfile = write_log(tmp_path, lines)
    non_empty_line_count = sum(1 for line in lines if line != "")

    counts = loglens.count_log_levels(logfile)

    assert sum(counts.values()) == non_empty_line_count


def test_count_command_exit_code_and_output(tmp_path, capsys):
    logfile = write_log(
        tmp_path,
        [
            "2026-07-18 09:12:03 INFO Server started on port 8080",
            "2026-07-18 09:12:05 WARN Disk usage high",
            "2026-07-18 09:12:10 ERROR Failed to connect to database",
            "garbage line",
        ],
    )

    args = argparse.Namespace(logfile=logfile)
    exit_code = loglens.cmd_count(args)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "ERROR : 1" in out
    assert "WARN  : 1" in out
    assert "INFO  : 1" in out
    assert "OTHER : 1" in out
    assert "TOTAL : 4" in out


def test_missing_file_returns_exit_code_1(tmp_path, capsys):
    missing_path = str(tmp_path / "does_not_exist.log")

    args = argparse.Namespace(logfile=missing_path)
    exit_code = loglens.cmd_count(args)
    err = capsys.readouterr().err

    assert exit_code == 1
    assert "not found" in err


def test_count_command_with_level_prints_only_that_level(tmp_path, capsys):
    logfile = write_log(
        tmp_path,
        [
            "2026-07-18 09:12:03 INFO Server started on port 8080",
            "2026-07-18 09:12:05 WARN Disk usage high",
            "2026-07-18 09:12:10 ERROR Failed to connect to database",
            "2026-07-18 09:12:20 ERROR Timeout occurred",
            "garbage line",
        ],
    )

    args = argparse.Namespace(logfile=logfile, level="ERROR")
    exit_code = loglens.cmd_count(args)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == "ERROR 2\n"


def test_count_command_with_level_other(tmp_path, capsys):
    logfile = write_log(
        tmp_path,
        [
            "2026-07-18 09:12:03 INFO Server started on port 8080",
            "garbage line",
            "another garbage line",
        ],
    )

    args = argparse.Namespace(logfile=logfile, level="OTHER")
    exit_code = loglens.cmd_count(args)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == "OTHER 2\n"


def test_count_command_with_level_zero_count(tmp_path, capsys):
    logfile = write_log(
        tmp_path,
        ["2026-07-18 09:12:03 INFO Server started on port 8080"],
    )

    args = argparse.Namespace(logfile=logfile, level="WARN")
    exit_code = loglens.cmd_count(args)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == "WARN 0\n"


def test_parser_accepts_level_option():
    parser = loglens.build_parser()

    args = parser.parse_args(["count", "sample.log", "--level", "INFO"])

    assert args.logfile == "sample.log"
    assert args.level == "INFO"


def test_parser_rejects_invalid_level(capsys):
    parser = loglens.build_parser()

    try:
        parser.parse_args(["count", "sample.log", "--level", "DEBUG"])
    except SystemExit as e:
        assert e.code == 2
    else:
        raise AssertionError("invalid level should be rejected")


RANGE_LINES = [
    "2026-07-18 09:12:03 INFO Server started on port 8080",
    "2026-07-18 09:12:05 WARN Disk usage high",
    "2026-07-18 09:12:07 ERROR Failed to connect to database",
    "Traceback (most recent call last):",
    "2026-07-18 09:12:09 INFO Request handled",
    "2026-07-18 09:12:11 ERROR Timeout occurred",
]


def test_time_range_is_inclusive_and_excludes_other(tmp_path):
    logfile = write_log(tmp_path, RANGE_LINES)

    counts = loglens.count_log_levels(logfile, since="09:12:05", until="09:12:09")

    assert counts["WARN"] == 1
    assert counts["ERROR"] == 1
    assert counts["INFO"] == 1
    assert counts.get("OTHER", 0) == 0


def test_since_only(tmp_path):
    logfile = write_log(tmp_path, RANGE_LINES)

    counts = loglens.count_log_levels(logfile, since="09:12:09")

    assert counts["INFO"] == 1
    assert counts["ERROR"] == 1
    assert sum(counts.values()) == 2


def test_until_only(tmp_path):
    logfile = write_log(tmp_path, RANGE_LINES)

    counts = loglens.count_log_levels(logfile, until="09:12:05")

    assert counts["INFO"] == 1
    assert counts["WARN"] == 1
    assert sum(counts.values()) == 2


def test_count_command_with_time_range_and_level(tmp_path, capsys):
    logfile = write_log(tmp_path, RANGE_LINES)

    parser = loglens.build_parser()
    args = parser.parse_args(
        ["count", logfile, "--since", "09:12:05", "--until", "09:12:09",
         "--level", "ERROR"]
    )
    exit_code = args.func(args)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == "ERROR 1\n"


def test_count_command_with_time_range_and_level_other(tmp_path, capsys):
    logfile = write_log(tmp_path, RANGE_LINES)

    args = argparse.Namespace(
        logfile=logfile, level="OTHER", since="09:00:00", until=None
    )
    exit_code = loglens.cmd_count(args)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == "OTHER 0\n"


def test_parser_rejects_invalid_time():
    parser = loglens.build_parser()

    try:
        parser.parse_args(["count", "sample.log", "--since", "9:12"])
    except SystemExit as e:
        assert e.code == 2
    else:
        raise AssertionError("invalid time should be rejected")


def jsonl_line(timestamp="2026-07-18 09:12:03", level="INFO", message="msg"):
    return json.dumps({"timestamp": timestamp, "level": level, "message": message})


def test_jsonl_counts_valid_lines_by_level(tmp_path):
    logfile = write_jsonl_log(
        tmp_path,
        [
            jsonl_line(level="INFO"),
            jsonl_line(level="WARN"),
            jsonl_line(level="ERROR"),
            jsonl_line(level="INFO"),
        ],
    )

    counts = loglens.count_log_levels(logfile)

    assert counts["INFO"] == 2
    assert counts["WARN"] == 1
    assert counts["ERROR"] == 1
    assert counts.get("OTHER", 0) == 0


def test_jsonl_counts_other_for_malformed_lines(tmp_path):
    logfile = write_jsonl_log(
        tmp_path,
        [
            jsonl_line(level="INFO"),
            "this is not json",
            '{"level": "WARN", "message": "missing timestamp key"}',
            '{"timestamp": "2026-07-18 09:16:45", "message": "missing level key"}',
            '{"timestamp": "2026-07-18 09:17:03", "level": "DEBUG", "message": "bad level"}',
        ],
    )

    counts = loglens.count_log_levels(logfile)

    assert counts["INFO"] == 1
    assert counts["OTHER"] == 4


def test_jsonl_total_matches_non_empty_line_count(tmp_path):
    lines = [
        jsonl_line(level="INFO"),
        "this is not json",
        "",
        jsonl_line(level="ERROR"),
        "",
        '{"level": "WARN", "message": "missing timestamp key"}',
    ]
    logfile = write_jsonl_log(tmp_path, lines)
    non_empty_line_count = sum(1 for line in lines if line != "")

    counts = loglens.count_log_levels(logfile)

    assert sum(counts.values()) == non_empty_line_count


def test_jsonl_count_command_with_level(tmp_path, capsys):
    logfile = write_jsonl_log(
        tmp_path,
        [
            jsonl_line(level="INFO"),
            jsonl_line(level="ERROR"),
            jsonl_line(level="ERROR"),
        ],
    )

    args = argparse.Namespace(logfile=logfile, level="ERROR")
    exit_code = loglens.cmd_count(args)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == "ERROR 2\n"


JSONL_RANGE_LINES = [
    jsonl_line(timestamp="2026-07-18 09:12:03", level="INFO"),
    jsonl_line(timestamp="2026-07-18 09:12:05", level="WARN"),
    jsonl_line(timestamp="2026-07-18 09:12:07", level="ERROR"),
    "this is not json",
    jsonl_line(timestamp="2026-07-18 09:12:09", level="INFO"),
    jsonl_line(timestamp="2026-07-18 09:12:11", level="ERROR"),
]


def test_jsonl_time_range_is_inclusive_and_excludes_other(tmp_path):
    logfile = write_jsonl_log(tmp_path, JSONL_RANGE_LINES)

    counts = loglens.count_log_levels(logfile, since="09:12:05", until="09:12:09")

    assert counts["WARN"] == 1
    assert counts["ERROR"] == 1
    assert counts["INFO"] == 1
    assert counts.get("OTHER", 0) == 0


def test_jsonl_command_with_time_range_and_level(tmp_path, capsys):
    logfile = write_jsonl_log(tmp_path, JSONL_RANGE_LINES)

    parser = loglens.build_parser()
    args = parser.parse_args(
        ["count", logfile, "--since", "09:12:05", "--until", "09:12:09",
         "--level", "ERROR"]
    )
    exit_code = args.func(args)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == "ERROR 1\n"


SAMPLE_JSONL = str(Path(__file__).parent / "sample.jsonl")


def test_sample_jsonl_fixture_counts(capsys):
    args = argparse.Namespace(logfile=SAMPLE_JSONL)
    exit_code = loglens.cmd_count(args)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == (
        "ERROR : 2\n"
        "WARN  : 2\n"
        "INFO  : 4\n"
        "OTHER : 4\n"
        "TOTAL : 12\n"
    )


def test_sample_jsonl_fixture_time_range():
    counts = loglens.count_log_levels(SAMPLE_JSONL, since="09:13:00", until="09:20:05")

    assert counts["WARN"] == 1
    assert counts["ERROR"] == 2
    assert counts["INFO"] == 2
    assert counts.get("OTHER", 0) == 0


SAMPLE_LOG = str(Path(__file__).parent / "sample.log")


def test_count_files_sums_counts_across_files(tmp_path):
    log_path = write_log(
        tmp_path,
        [
            "2026-07-18 09:12:03 INFO Server started on port 8080",
            "2026-07-18 09:12:10 ERROR Failed to connect to database",
            "garbage line",
        ],
    )
    jsonl_path = write_jsonl_log(
        tmp_path,
        [
            jsonl_line(level="WARN"),
            jsonl_line(level="ERROR"),
            "this is not json",
            "",
        ],
    )

    counts = loglens.count_files([log_path, jsonl_path])

    assert counts["ERROR"] == 2
    assert counts["WARN"] == 1
    assert counts["INFO"] == 1
    assert counts["OTHER"] == 2
    assert sum(counts.values()) == 6


def test_count_files_applies_time_range_to_all_files(tmp_path):
    log_path = write_log(tmp_path, RANGE_LINES)
    jsonl_path = write_jsonl_log(tmp_path, JSONL_RANGE_LINES)

    counts = loglens.count_files(
        [log_path, jsonl_path], since="09:12:05", until="09:12:09"
    )

    assert counts["WARN"] == 2
    assert counts["ERROR"] == 2
    assert counts["INFO"] == 2
    assert counts.get("OTHER", 0) == 0


def test_parser_accepts_multiple_files():
    parser = loglens.build_parser()

    args = parser.parse_args(["count", "a.log", "b.jsonl", "c.log"])

    assert args.logfile == "a.log"
    assert args.more_logfiles == ["b.jsonl", "c.log"]


def test_parser_single_file_has_no_extra_files():
    parser = loglens.build_parser()

    args = parser.parse_args(["count", "a.log"])

    assert args.logfile == "a.log"
    assert args.more_logfiles == []


def test_count_command_multiple_files_output(capsys):
    parser = loglens.build_parser()
    args = parser.parse_args(["count", SAMPLE_LOG, SAMPLE_JSONL])
    exit_code = args.func(args)
    out = capsys.readouterr().out

    expected = loglens.count_log_levels(SAMPLE_LOG) + loglens.count_log_levels(
        SAMPLE_JSONL
    )
    assert exit_code == 0
    assert out == (
        f"ERROR : {expected['ERROR']}\n"
        f"WARN  : {expected['WARN']}\n"
        f"INFO  : {expected['INFO']}\n"
        f"OTHER : {expected['OTHER']}\n"
        f"TOTAL : {sum(expected.values())}\n"
    )


def test_count_command_multiple_files_with_level_and_time_range(tmp_path, capsys):
    log_path = write_log(tmp_path, RANGE_LINES)
    jsonl_path = write_jsonl_log(tmp_path, JSONL_RANGE_LINES)

    parser = loglens.build_parser()
    args = parser.parse_args(
        ["count", log_path, jsonl_path, "--since", "09:12:05",
         "--until", "09:12:09", "--level", "ERROR"]
    )
    exit_code = args.func(args)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == "ERROR 2\n"


def test_count_command_single_file_output_unchanged(capsys):
    parser = loglens.build_parser()
    args = parser.parse_args(["count", SAMPLE_JSONL])
    exit_code = args.func(args)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == (
        "ERROR : 2\n"
        "WARN  : 2\n"
        "INFO  : 4\n"
        "OTHER : 4\n"
        "TOTAL : 12\n"
    )


def test_count_command_multiple_files_missing_file(tmp_path, capsys):
    log_path = write_log(tmp_path, ["2026-07-18 09:12:03 INFO ok"])
    missing_path = str(tmp_path / "does_not_exist.jsonl")

    parser = loglens.build_parser()
    args = parser.parse_args(["count", log_path, missing_path])
    exit_code = args.func(args)
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "not found" in captured.err
    assert missing_path in captured.err


TOP_LINES = [
    "2026-07-18 09:12:03 INFO Request handled",
    "2026-07-18 09:12:05 ERROR Timeout occurred",
    "Traceback (most recent call last):",
    "Traceback (most recent call last):",
    "Traceback (most recent call last):",
    "2026-07-18 09:12:07 WARN Disk usage high",
    "2026-07-18 09:12:09 INFO Request handled",
    "2026-07-18 09:12:11 ERROR Timeout occurred",
    "2026-07-18 09:12:13 INFO Request handled",
    "2026-07-18 09:12:15 INFO Server started",
]


def run_count(argv):
    parser = loglens.build_parser()
    args = parser.parse_args(["count"] + argv)
    return args.func(args)


def test_count_messages_counts_by_message(tmp_path):
    logfile = write_log(tmp_path, TOP_LINES)

    messages = loglens.count_messages([logfile])

    assert messages == {
        "Request handled": 3,
        "Timeout occurred": 2,
        "Disk usage high": 1,
        "Server started": 1,
    }


def test_top_prints_after_level_counts(tmp_path, capsys):
    logfile = write_log(tmp_path, TOP_LINES)

    exit_code = run_count([logfile, "--top", "2"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == (
        "ERROR : 2\n"
        "WARN  : 1\n"
        "INFO  : 4\n"
        "OTHER : 3\n"
        "TOTAL : 10\n"
        "3 Request handled\n"
        "2 Timeout occurred\n"
    )


def test_top_ties_keep_first_appearance_order(tmp_path, capsys):
    logfile = write_log(
        tmp_path,
        [
            "2026-07-18 09:12:03 INFO bbb",
            "2026-07-18 09:12:04 INFO aaa",
            "2026-07-18 09:12:05 INFO ccc",
            "2026-07-18 09:12:06 INFO ccc",
            "2026-07-18 09:12:07 INFO aaa",
            "2026-07-18 09:12:08 INFO bbb",
            "2026-07-18 09:12:09 INFO ddd",
        ],
    )

    exit_code = run_count([logfile, "--top", "4", "--level", "INFO"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == "INFO 7\n2 bbb\n2 aaa\n2 ccc\n1 ddd\n"


def test_top_larger_than_message_kinds_prints_all(tmp_path, capsys):
    logfile = write_log(tmp_path, TOP_LINES)

    exit_code = run_count([logfile, "--top", "100"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out.splitlines()[5:] == [
        "3 Request handled",
        "2 Timeout occurred",
        "1 Disk usage high",
        "1 Server started",
    ]


def test_top_with_level_counts_only_that_level(tmp_path, capsys):
    logfile = write_log(tmp_path, TOP_LINES)

    exit_code = run_count([logfile, "--top", "5", "--level", "ERROR"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == "ERROR 2\n2 Timeout occurred\n"


def test_top_with_level_other_prints_no_messages(tmp_path, capsys):
    logfile = write_log(tmp_path, TOP_LINES)

    exit_code = run_count([logfile, "--top", "3", "--level", "OTHER"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == "OTHER 3\n"


def test_top_excludes_other_lines(tmp_path):
    logfile = write_log(tmp_path, TOP_LINES)

    messages = loglens.count_messages([logfile])

    assert "Traceback (most recent call last):" not in messages
    assert sum(messages.values()) == 7


def test_top_with_time_range(tmp_path, capsys):
    logfile = write_log(tmp_path, TOP_LINES)

    exit_code = run_count(
        [logfile, "--top", "3", "--since", "09:12:05", "--until", "09:12:11"]
    )
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == (
        "ERROR : 2\n"
        "WARN  : 1\n"
        "INFO  : 1\n"
        "OTHER : 0\n"
        "TOTAL : 4\n"
        "2 Timeout occurred\n"
        "1 Disk usage high\n"
        "1 Request handled\n"
    )


def test_top_with_jsonl_and_multiple_files(tmp_path, capsys):
    log_path = write_log(tmp_path, TOP_LINES)
    jsonl_path = write_jsonl_log(
        tmp_path,
        [
            jsonl_line(level="WARN", message="Disk usage high"),
            jsonl_line(level="WARN", message="Disk usage high"),
            jsonl_line(level="DEBUG", message="Disk usage high"),
            "this is not json",
        ],
    )

    exit_code = run_count([log_path, jsonl_path, "--top", "2", "--level", "WARN"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == "WARN 3\n3 Disk usage high\n"


def test_top_sample_jsonl(capsys):
    exit_code = run_count([SAMPLE_JSONL, "--top", "1", "--level", "INFO"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == "INFO 4\n1 Server started on port 8080\n"


def test_count_without_top_prints_no_messages(capsys):
    exit_code = run_count([SAMPLE_LOG])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out.splitlines()[-1].startswith("TOTAL")


def test_parser_accepts_top_option():
    parser = loglens.build_parser()

    args = parser.parse_args(["count", "sample.log", "--top", "3"])

    assert args.top == 3


def test_parser_rejects_invalid_top():
    parser = loglens.build_parser()

    for value in ["0", "-1", "abc"]:
        try:
            parser.parse_args(["count", "sample.log", "--top", value])
        except SystemExit as e:
            assert e.code == 2
        else:
            raise AssertionError(f"--top {value} should be rejected")


def test_format_json_prints_counts_and_total(capsys):
    exit_code = run_count([SAMPLE_LOG, "--format", "json"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == (
        "{\n"
        '  "counts": {\n'
        '    "ERROR": 3,\n'
        '    "WARN": 4,\n'
        '    "INFO": 11,\n'
        '    "OTHER": 2\n'
        "  },\n"
        '  "total": 20\n'
        "}\n"
    )


def test_format_json_key_order(capsys):
    run_count([SAMPLE_LOG, "--format", "json", "--top", "2"])
    data = json.loads(capsys.readouterr().out)

    assert list(data) == ["counts", "total", "top"]
    assert list(data["counts"]) == ["ERROR", "WARN", "INFO", "OTHER"]


def test_format_json_with_top(tmp_path, capsys):
    logfile = write_log(tmp_path, TOP_LINES)

    exit_code = run_count([logfile, "--format", "json", "--top", "2"])
    data = json.loads(capsys.readouterr().out)

    expected_messages = loglens.count_messages([logfile]).most_common(2)
    assert exit_code == 0
    assert data["top"] == [
        {"count": count, "message": message}
        for message, count in expected_messages
    ]
    assert list(data["top"][0]) == ["count", "message"]


def test_format_json_without_top_has_no_top_key(capsys):
    run_count([SAMPLE_LOG, "--format", "json"])
    data = json.loads(capsys.readouterr().out)

    assert "top" not in data


def test_format_json_with_level(tmp_path, capsys):
    logfile = write_log(tmp_path, TOP_LINES)

    exit_code = run_count([logfile, "--format", "json", "--level", "ERROR"])
    data = json.loads(capsys.readouterr().out)

    expected = loglens.count_log_levels(logfile)["ERROR"]
    assert exit_code == 0
    assert data == {"counts": {"ERROR": expected}, "total": expected}


def test_format_json_with_time_range_jsonl_and_multiple_files(tmp_path, capsys):
    log_path = write_log(tmp_path, RANGE_LINES)
    jsonl_path = write_jsonl_log(tmp_path, JSONL_RANGE_LINES)
    argv = [log_path, jsonl_path, "--since", "09:12:05", "--until", "09:12:09"]

    exit_code = run_count(argv + ["--format", "json"])
    data = json.loads(capsys.readouterr().out)

    expected = loglens.count_files(
        [log_path, jsonl_path], since="09:12:05", until="09:12:09"
    )
    assert exit_code == 0
    assert data["counts"] == {name: expected.get(name, 0) for name in loglens.LEVELS}
    assert data["total"] == sum(expected.values())


def test_format_text_matches_default_output(capsys):
    run_count([SAMPLE_LOG, SAMPLE_JSONL, "--top", "3"])
    default_out = capsys.readouterr().out
    run_count([SAMPLE_LOG, SAMPLE_JSONL, "--top", "3", "--format", "text"])
    text_out = capsys.readouterr().out

    assert text_out == default_out


def test_parser_format_defaults_to_text():
    args = loglens.build_parser().parse_args(["count", "a.log"])

    assert args.format == "text"


def test_parser_rejects_unknown_format():
    parser = loglens.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["count", "a.log", "--format", "xml"])


def test_format_csv_prints_header_and_counts(capsys):
    exit_code = run_count([SAMPLE_LOG, "--format", "csv"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == (
        "level,count\n"
        "ERROR,3\n"
        "WARN,4\n"
        "INFO,11\n"
        "OTHER,2\n"
        "TOTAL,20\n"
    )


def test_format_csv_with_top(tmp_path, capsys):
    logfile = write_log(tmp_path, TOP_LINES)

    exit_code = run_count([logfile, "--format", "csv", "--top", "2"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == (
        "level,count\n"
        "ERROR,2\n"
        "WARN,1\n"
        "INFO,4\n"
        "OTHER,3\n"
        "TOTAL,10\n"
        "\n"
        "count,message\n"
        "3,Request handled\n"
        "2,Timeout occurred\n"
    )


def test_format_csv_quotes_messages_with_comma_and_quote(tmp_path, capsys):
    logfile = write_log(
        tmp_path,
        [
            '2026-07-18 09:12:03 ERROR Failed: a,b "x"',
            '2026-07-18 09:12:04 ERROR Failed: a,b "x"',
            "2026-07-18 09:12:05 INFO plain",
        ],
    )

    exit_code = run_count([logfile, "--format", "csv", "--top", "2"])
    lines = capsys.readouterr().out.splitlines()

    assert exit_code == 0
    assert lines[6:] == ["", "count,message", '2,"Failed: a,b ""x"""', "1,plain"]


def test_format_csv_with_level(tmp_path, capsys):
    logfile = write_log(tmp_path, TOP_LINES)

    exit_code = run_count([logfile, "--format", "csv", "--level", "ERROR", "--top", "5"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == (
        "level,count\n"
        "ERROR,2\n"
        "TOTAL,2\n"
        "\n"
        "count,message\n"
        "2,Timeout occurred\n"
    )


def test_format_csv_with_time_range_jsonl_and_multiple_files(tmp_path, capsys):
    log_path = write_log(tmp_path, RANGE_LINES)
    jsonl_path = write_jsonl_log(tmp_path, JSONL_RANGE_LINES)
    argv = [log_path, jsonl_path, "--since", "09:12:05", "--until", "09:12:09"]

    exit_code = run_count(argv + ["--format", "csv"])
    out = capsys.readouterr().out

    expected = loglens.count_files(
        [log_path, jsonl_path], since="09:12:05", until="09:12:09"
    )
    assert exit_code == 0
    assert out.splitlines() == (
        ["level,count"]
        + [f"{name},{expected.get(name, 0)}" for name in loglens.LEVELS]
        + [f"TOTAL,{sum(expected.values())}"]
    )


def test_format_csv_missing_file_returns_exit_code_1(tmp_path, capsys):
    exit_code = run_count([str(tmp_path / "missing.log"), "--format", "csv"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""


def test_parser_accepts_csv_format():
    args = loglens.build_parser().parse_args(["count", "a.log", "--format", "csv"])

    assert args.format == "csv"


# --- --regex ---

REGEX_LINES = [
    "2026-07-18 09:00:01 ERROR Connection timeout",
    "2026-07-18 09:00:02 ERROR Connection refused",
    "2026-07-18 09:00:03 WARN Retry after timeout",
    "2026-07-18 09:00:04 INFO Request handled",
    "Traceback (most recent call last):",
    "2026-07-18 09:00:05 INFO TIMEOUT reset",
    "2026-07-18 09:00:06 ERROR Connection timeout",
]


def test_regex_filters_counts_by_message(tmp_path, capsys):
    logfile = write_log(tmp_path, REGEX_LINES)

    exit_code = run_count([str(logfile), "--regex", "timeout|refused"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out.splitlines() == [
        "ERROR : 3",
        "WARN  : 1",
        "INFO  : 0",
        "OTHER : 0",
        "TOTAL : 4",
    ]


def test_regex_is_case_sensitive_and_uses_search(tmp_path):
    logfile = write_log(tmp_path, REGEX_LINES)

    counts = loglens.count_files([logfile], pattern=loglens.re.compile("TIMEOUT"))
    assert counts == {"INFO": 1}

    counts = loglens.count_files([logfile], pattern=loglens.re.compile("^Retry"))
    assert counts == {"WARN": 1}


def test_regex_with_level(tmp_path, capsys):
    logfile = write_log(tmp_path, REGEX_LINES)

    exit_code = run_count([str(logfile), "--regex", "timeout", "--level", "ERROR"])

    assert exit_code == 0
    assert capsys.readouterr().out == "ERROR 2\n"


def test_regex_with_level_other_is_zero(tmp_path, capsys):
    logfile = write_log(tmp_path, REGEX_LINES)

    exit_code = run_count([str(logfile), "--regex", ".*", "--level", "OTHER"])

    assert exit_code == 0
    assert capsys.readouterr().out == "OTHER 0\n"


def test_regex_with_time_range(tmp_path, capsys):
    logfile = write_log(tmp_path, REGEX_LINES)

    exit_code = run_count(
        [str(logfile), "--regex", "timeout", "--since", "09:00:02", "--until", "09:00:05"]
    )
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out.splitlines()[-1] == "TOTAL : 1"
    assert out.splitlines()[1] == "WARN  : 1"


def test_regex_with_top(tmp_path, capsys):
    logfile = write_log(tmp_path, REGEX_LINES)

    exit_code = run_count([str(logfile), "--regex", "^Connection", "--top", "5"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out.splitlines()[-2:] == [
        "2 Connection timeout",
        "1 Connection refused",
    ]


def test_regex_with_format_json(tmp_path, capsys):
    logfile = write_log(tmp_path, REGEX_LINES)

    exit_code = run_count(
        [str(logfile), "--regex", "refused", "--format", "json", "--top", "1"]
    )
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert result == {
        "counts": {"ERROR": 1, "WARN": 0, "INFO": 0, "OTHER": 0},
        "total": 1,
        "top": [{"count": 1, "message": "Connection refused"}],
    }


def test_regex_with_format_csv(tmp_path, capsys):
    logfile = write_log(tmp_path, REGEX_LINES)

    exit_code = run_count([str(logfile), "--regex", "Request", "--format", "csv"])

    assert exit_code == 0
    assert capsys.readouterr().out.splitlines() == [
        "level,count",
        "ERROR,0",
        "WARN,0",
        "INFO,1",
        "OTHER,0",
        "TOTAL,1",
    ]


def test_regex_with_jsonl_and_multiple_files(tmp_path, capsys):
    log_path = write_log(tmp_path, REGEX_LINES)
    jsonl_path = write_jsonl_log(
        tmp_path,
        [
            jsonl_line(level="ERROR", message="Upstream timeout"),
            jsonl_line(level="INFO", message="ok"),
            "not json",
        ],
    )

    exit_code = run_count(
        [str(log_path), str(jsonl_path), "--regex", "timeout", "--level", "ERROR"]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == "ERROR 3\n"


def test_regex_invalid_pattern_exits_2(tmp_path, capsys):
    logfile = write_log(tmp_path, REGEX_LINES)

    exit_code = run_count([str(logfile), "--regex", "(unclosed"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "(unclosed" in captured.err
    assert "missing )" in captured.err


def test_parser_regex_defaults_to_none():
    args = loglens.build_parser().parse_args(["count", "a.log"])

    assert args.regex is None



# --- --stats ---

STATS_LINES = [
    "2026-07-18 09:00:01 ERROR Connection timeout",
    "2026-07-18 09:15:00 INFO Request handled",
    "2026-07-18 10:00:00 WARN Disk usage high",
    "Traceback (most recent call last):",
    "2026-07-18 10:30:00 INFO Request handled",
    "2026-07-18 23:59:59 ERROR Timeout",
]


def test_stats_prints_blank_line_and_hourly_breakdown(tmp_path, capsys):
    logfile = write_log(tmp_path, STATS_LINES)

    exit_code = run_count([logfile, "--stats"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out.splitlines() == [
        "ERROR : 2",
        "WARN  : 1",
        "INFO  : 2",
        "OTHER : 1",
        "TOTAL : 6",
        "",
        "09時 2件",
        "10時 2件",
        "23時 1件",
    ]


def test_stats_without_flag_output_unchanged(tmp_path, capsys):
    logfile = write_log(tmp_path, STATS_LINES)

    run_count([logfile])
    without_stats = capsys.readouterr().out
    run_count([logfile, "--stats"])
    with_stats = capsys.readouterr().out

    assert with_stats.startswith(without_stats)
    assert with_stats != without_stats


def test_stats_excludes_other_lines(tmp_path):
    logfile = write_log(tmp_path, STATS_LINES)

    hourly = loglens.count_hourly([logfile])

    assert sum(hourly.values()) == 5
    assert hourly == {"09": 2, "10": 2, "23": 1}


def test_stats_with_level_filters_hours(tmp_path, capsys):
    logfile = write_log(tmp_path, STATS_LINES)

    exit_code = run_count([logfile, "--level", "ERROR", "--stats"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out.splitlines() == [
        "ERROR 2",
        "",
        "09時 1件",
        "23時 1件",
    ]


def test_stats_with_level_no_matches_prints_only_blank_line(tmp_path, capsys):
    logfile = write_log(tmp_path, STATS_LINES)

    exit_code = run_count(
        [
            logfile,
            "--level",
            "WARN",
            "--since",
            "00:00:00",
            "--until",
            "01:00:00",
            "--stats",
        ]
    )
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == "WARN 0\n\n"


def test_stats_with_time_range(tmp_path, capsys):
    logfile = write_log(tmp_path, STATS_LINES)

    exit_code = run_count(
        [logfile, "--since", "09:30:00", "--until", "22:00:00", "--stats"]
    )
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out.splitlines()[-1] == "10時 2件"
    assert "09時" not in out
    assert "23時" not in out


def test_stats_with_regex(tmp_path, capsys):
    logfile = write_log(tmp_path, STATS_LINES)

    exit_code = run_count([logfile, "--regex", "(?i)timeout", "--stats"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out.splitlines()[-2:] == ["09時 1件", "23時 1件"]


def test_stats_hour_is_zero_padded(tmp_path, capsys):
    logfile = write_log(
        tmp_path,
        [
            "2026-07-18 00:05:00 INFO Midnight event",
            "2026-07-18 00:45:00 INFO Another midnight event",
        ],
    )

    exit_code = run_count([logfile, "--stats"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out.splitlines()[-1] == "00時 2件"


def test_stats_sums_across_multiple_files(tmp_path, capsys):
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    log_a = write_log(dir_a, ["2026-07-18 09:00:00 INFO one"])
    dir_b = tmp_path / "b"
    dir_b.mkdir()
    log_b = write_log(dir_b, ["2026-07-18 09:30:00 INFO two"])

    exit_code = run_count([log_a, log_b, "--stats"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out.splitlines()[-1] == "09時 2件"


def test_stats_with_jsonl(tmp_path, capsys):
    jsonl_path = write_jsonl_log(
        tmp_path,
        [
            jsonl_line(timestamp="2026-07-18 11:00:00", level="INFO"),
            jsonl_line(timestamp="2026-07-18 11:30:00", level="WARN"),
        ],
    )

    exit_code = run_count([jsonl_path, "--stats"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out.splitlines()[-1] == "11時 2件"


def test_stats_with_top_prints_after_top_messages(tmp_path, capsys):
    logfile = write_log(tmp_path, STATS_LINES)

    exit_code = run_count([logfile, "--top", "1", "--stats"])
    out = capsys.readouterr().out.splitlines()

    assert exit_code == 0
    assert out[5] == "2 Request handled"
    assert out[6] == ""
    assert out[7:] == ["09時 2件", "10時 2件", "23時 1件"]


def test_stats_format_json_adds_stats_key_last(tmp_path, capsys):
    logfile = write_log(tmp_path, STATS_LINES)

    exit_code = run_count([logfile, "--format", "json", "--stats"])
    data = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert list(data) == ["counts", "total", "stats"]
    assert data["stats"] == {"09": 2, "10": 2, "23": 1}
    assert list(data["stats"]) == ["09", "10", "23"]


def test_stats_format_json_with_top_key_order(tmp_path, capsys):
    logfile = write_log(tmp_path, STATS_LINES)

    exit_code = run_count([logfile, "--format", "json", "--top", "1", "--stats"])
    data = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert list(data) == ["counts", "total", "top", "stats"]


def test_stats_format_json_without_stats_has_no_stats_key(capsys):
    run_count([SAMPLE_LOG, "--format", "json"])
    data = json.loads(capsys.readouterr().out)

    assert "stats" not in data


def test_stats_with_format_csv_exits_2(tmp_path, capsys):
    logfile = write_log(tmp_path, STATS_LINES)

    exit_code = run_count([logfile, "--format", "csv", "--stats"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert captured.err != ""


def test_parser_accepts_stats_flag():
    args = loglens.build_parser().parse_args(["count", "a.log", "--stats"])

    assert args.stats is True


def test_parser_stats_defaults_to_false():
    args = loglens.build_parser().parse_args(["count", "a.log"])

    assert args.stats is False


# --- --output ---


def test_output_writes_text_report_and_prints_wrote_message(tmp_path, capsys):
    logfile = write_log(tmp_path, TOP_LINES)
    out_path = tmp_path / "result.txt"

    exit_code = run_count([str(logfile), "--output", str(out_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == f"wrote: {out_path}\n"
    assert captured.err == ""

    stdout_exit_code = run_count([str(logfile)])
    expected = capsys.readouterr().out
    assert stdout_exit_code == 0
    assert out_path.read_text(encoding="utf-8") == expected


def test_output_writes_json_report(tmp_path, capsys):
    logfile = write_log(tmp_path, TOP_LINES)
    out_path = tmp_path / "result.json"

    exit_code = run_count(
        [str(logfile), "--format", "json", "--top", "2", "--output", str(out_path)]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == f"wrote: {out_path}\n"

    stdout_exit_code = run_count([str(logfile), "--format", "json", "--top", "2"])
    expected = capsys.readouterr().out
    assert stdout_exit_code == 0
    assert out_path.read_text(encoding="utf-8") == expected


def test_output_writes_csv_report(tmp_path, capsys):
    logfile = write_log(tmp_path, TOP_LINES)
    out_path = tmp_path / "result.csv"

    exit_code = run_count([str(logfile), "--format", "csv", "--output", str(out_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == f"wrote: {out_path}\n"

    stdout_exit_code = run_count([str(logfile), "--format", "csv"])
    expected = capsys.readouterr().out
    assert stdout_exit_code == 0
    assert out_path.read_text(encoding="utf-8") == expected


def test_output_file_is_utf8_and_ends_with_newline(tmp_path):
    logfile = write_log(
        tmp_path, ["2026-07-18 09:12:03 INFO 日本語メッセージ"]
    )
    out_path = tmp_path / "result.txt"

    exit_code = run_count([str(logfile), "--output", str(out_path)])

    assert exit_code == 0
    content = out_path.read_bytes().decode("utf-8")
    assert content.endswith("\n")
    assert "日本語メッセージ" not in content


def test_output_overwrites_existing_file(tmp_path, capsys):
    logfile = write_log(tmp_path, TOP_LINES)
    out_path = tmp_path / "result.txt"
    out_path.write_text("old content that should be replaced\n", encoding="utf-8")

    exit_code = run_count([str(logfile), "--output", str(out_path)])
    capsys.readouterr()

    assert exit_code == 0
    assert "old content" not in out_path.read_text(encoding="utf-8")


def test_output_missing_parent_directory_errors(tmp_path, capsys):
    logfile = write_log(tmp_path, TOP_LINES)
    out_path = tmp_path / "does" / "not" / "exist" / "result.txt"

    exit_code = run_count([str(logfile), "--output", str(out_path)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.startswith("error:")
    assert not out_path.exists()


def test_output_not_given_leaves_stdout_unchanged(capsys):
    exit_code_without = run_count([SAMPLE_LOG])
    out_without = capsys.readouterr().out

    args = loglens.build_parser().parse_args(["count", SAMPLE_LOG])
    exit_code_with_default = args.func(args)
    out_with_default = capsys.readouterr().out

    assert exit_code_without == exit_code_with_default == 0
    assert out_without == out_with_default


def test_parser_output_defaults_to_none():
    args = loglens.build_parser().parse_args(["count", "a.log"])

    assert args.output is None


def test_parser_accepts_output_option():
    args = loglens.build_parser().parse_args(
        ["count", "a.log", "--output", "result.txt"]
    )

    assert args.output == "result.txt"
