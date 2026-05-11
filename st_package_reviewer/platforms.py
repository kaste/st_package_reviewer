PLATFORM_ALL = "all"
PLATFORM_ORDER = ("windows", "linux", "osx")


def normalize_platforms(platforms=PLATFORM_ALL):
    values = _platform_values(platforms)
    normalized = []
    for value in values:
        platform = _normalize_platform(value)
        if platform == PLATFORM_ALL:
            return (PLATFORM_ALL,)
        if platform and platform not in normalized:
            normalized.append(platform)

    if not normalized:
        return (PLATFORM_ALL,)

    return tuple(
        platform for platform in PLATFORM_ORDER
        if platform in normalized
    )


def format_platforms(platforms=PLATFORM_ALL):
    return ",".join(normalize_platforms(platforms))


def platforms_include(platforms, platform):
    normalized = normalize_platforms(platforms)
    platform = _normalize_platform(platform)
    return PLATFORM_ALL in normalized or platform in normalized


def _platform_values(platforms):
    if platforms is None:
        return [PLATFORM_ALL]
    if isinstance(platforms, str):
        return _split_platform_value(platforms)
    if isinstance(platforms, (list, tuple, set)):
        values = []
        for item in platforms:
            if isinstance(item, str):
                values.extend(_split_platform_value(item))
        return values
    return [PLATFORM_ALL]


def _split_platform_value(value):
    return [part.strip() for part in value.split(",") if part.strip()]


def _normalize_platform(value):
    value = value.casefold().strip()
    if value in ("*", PLATFORM_ALL):
        return PLATFORM_ALL

    platform = value.split("-", 1)[0]
    if platform in PLATFORM_ORDER:
        return platform
    return None
