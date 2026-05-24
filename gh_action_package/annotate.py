from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Iterable, TextIO


HEADER_RE = re.compile(r"^(Reporting )?[0-9]+ (failure|warning)s?:$")
FILE_RE = re.compile(r"^\s+File: (.+)$")
LINE_RE = re.compile(r"^\s+Line: ([0-9]+)(?:, Column: ([0-9]+))?$")


@dataclass
class Annotation:
    severity: str
    message: str = ""
    file: str = ""
    line: str = ""
    col: str = ""


def main() -> int:
    annotate_output(sys.stdin, sys.stdout)
    return 0


def annotate_output(lines: Iterable[str], out: TextIO) -> None:
    line_iter = iter(lines)
    for raw_line in line_iter:
        line = raw_line.rstrip("\n")
        print(raw_line, end="", file=out)

        header_match = HEADER_RE.match(line)
        if not header_match:
            continue

        severity = "error" if header_match.group(2) == "failure" else "warning"
        annotation = Annotation(severity)

        for raw_line in line_iter:
            line = raw_line.rstrip("\n")

            if line == "":
                print(raw_line, end="", file=out)
                break

            if line.startswith("- "):
                if annotation.message:
                    emit_annotation(annotation, out)
                annotation = Annotation(severity, message=line[2:])
            elif file_match := FILE_RE.match(line):
                annotation.file = file_match.group(1)
            elif line_match := LINE_RE.match(line):
                annotation.line = line_match.group(1)
                annotation.col = line_match.group(2) or ""

            print(raw_line, end="", file=out)

        if annotation.message:
            emit_annotation(annotation, out)


def emit_annotation(annotation: Annotation, out: TextIO) -> None:
    properties = ["title=CHECK"]
    if annotation.file:
        properties.append(f"file={escape_property(annotation.file)}")
    if annotation.line:
        properties.append(f"line={escape_property(annotation.line)}")
    if annotation.col:
        properties.append(f"col={escape_property(annotation.col)}")

    message = escape_data(annotation.message)
    print(f"::{annotation.severity} {','.join(properties)}::{message}", file=out)


def escape_property(data: str) -> str:
    return escape_data(data).replace(":", "%3A").replace(",", "%2C")


def escape_data(data: str) -> str:
    return data.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


if __name__ == "__main__":
    raise SystemExit(main())
