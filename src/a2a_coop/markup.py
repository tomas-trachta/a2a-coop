import re
from typing import NamedTuple, Optional

FENCE = re.compile(r"^\s*(`{3,})\s*([\w+#.-]*)")
MAX_LIST_LEVEL = 3
BULLET = "•"

BULLET_ITEM = re.compile(r"^(\s*)[-*+]\s+(.*)$")
NUMBERED_ITEM = re.compile(r"^(\s*)(\d+[.)])\s+(.*)$")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
INLINE = re.compile(r"`([^`\n]+)`|\*\*([^*\n]+)\*\*")


class Span(NamedTuple):
    text: str
    style: str = ""


class Line(NamedTuple):
    kind: str
    spans: tuple[Span, ...]
    marker: str = ""
    level: int = 0
    gap: bool = False
    continued: bool = False
    language: str = ""


def parse(body: str) -> list[Line]:
    lines: list[Line] = []
    code: Optional[list[str]] = None
    fence = language = ""
    gap = False

    for raw in body.strip().splitlines():
        if code is not None:
            if raw.strip().startswith(fence) and not raw.strip().strip("`"):
                lines.append(Line("code", (Span("\n".join(code), "code"),), gap=gap, language=language))
                code, gap = None, False
            else:
                code.append(raw)
            continue

        if match := FENCE.match(raw):
            code, fence, language = [], match.group(1), match.group(2).lower()
            gap = gap or bool(lines)
            continue

        if not raw.strip():
            gap = bool(lines)
            continue

        previous = lines[-1] if lines else None

        if previous is not None and previous.kind == "item" and not gap and raw[:1].isspace() and not is_item(raw):
            lines.append(previous._replace(spans=spans(raw.strip()), gap=False, continued=True))
            continue

        lines.append(parse_line(raw, gap))
        gap = False

    if code is not None:
        lines.append(Line("code", (Span("\n".join(code), "code"),), gap=gap, language=language))

    return lines


def fence(code: str, language: str = "") -> str:
    longest = max((len(run) for run in re.findall(r"`+", code)), default=0)
    marker = "`" * max(3, longest + 1)

    return f"{marker}{language.strip()}\n{code.rstrip()}\n{marker}"


def parse_line(raw: str, gap: bool) -> Line:
    if match := BULLET_ITEM.match(raw):
        return Line("item", spans(match.group(2)), BULLET, list_level(match.group(1)), gap)

    if match := NUMBERED_ITEM.match(raw):
        return Line("item", spans(match.group(3)), match.group(2), list_level(match.group(1)), gap)

    if match := HEADING.match(raw):
        return Line("heading", spans(match.group(1)), gap=gap)

    return Line("text", spans(raw.rstrip()), gap=gap)


def is_item(raw: str) -> bool:
    return bool(BULLET_ITEM.match(raw) or NUMBERED_ITEM.match(raw))


def list_level(indent: str) -> int:
    return min(len(indent.expandtabs(4)) // 2, MAX_LIST_LEVEL)


def spans(text: str) -> tuple[Span, ...]:
    result: list[Span] = []
    position = 0

    for match in INLINE.finditer(text):
        if match.start() > position:
            result.append(Span(text[position : match.start()]))

        code, strong = match.groups()
        result.append(Span(code, "code") if code is not None else Span(strong, "strong"))
        position = match.end()

    if position < len(text):
        result.append(Span(text[position:]))

    return tuple(result)
