"""Given a list of route patterns and a path, report which pattern matches.

Route file format (one pattern per line):

    /                      home
    /users                 users.list
    /users/:id             users.show
    /users/:id:int/posts/:pid:int  users.post.show
    /static/*path          static.serve

Segments starting with ':' capture a single path segment. A named
segment may carry a type, written ':name:type' (for example ':id:int').
A segment that fails its type check does not match, the same as a
literal segment mismatch. Plain ':name' is equivalent to ':name:str'
and accepts anything. A segment starting with '*' must be the last one
and captures everything remaining, slashes included, and is always a
string. Everything else must match literally. Lines starting with '#'
and blank lines are ignored. The text after the pattern (if any) is
treated as a free-form route name and is only used for display.

Matching follows first-registered-wins, the same rule most routers use,
but this tool also tells you when a later pattern would have matched too,
since that's usually the thing you're actually trying to debug.
"""

import argparse
import json
import re
import sys

_INT_RE = re.compile(r"-?\d+")

# Each type maps to a predicate over the raw path segment and a converter
# applied once the predicate passes.
PARAM_TYPES = {
    "str": (lambda value: True, str),
    "int": (lambda value: bool(_INT_RE.fullmatch(value)), int),
}


class RouteError(ValueError):
    def __init__(self, line_no, message):
        super().__init__(f"line {line_no}: {message}")
        self.line_no = line_no


class Route:
    def __init__(self, pattern, name, line_no):
        self.pattern = pattern
        self.name = name
        self.line_no = line_no
        self.segments = _parse_segments(_split_path(pattern), line_no)

    def match(self, path_segments):
        params = {}
        for i, (kind, value, type_name) in enumerate(self.segments):
            if kind == "wildcard":
                remainder = path_segments[i:]
                if not remainder:
                    return None
                params[value] = "/".join(remainder)
                return params
            if i >= len(path_segments):
                return None
            seg = path_segments[i]
            if kind == "param":
                predicate, convert = PARAM_TYPES[type_name]
                if not predicate(seg):
                    return None
                params[value] = convert(seg)
            elif seg != value:
                return None
        if len(path_segments) != len(self.segments):
            return None
        return params


def _split_path(path):
    return [seg for seg in path.strip("/").split("/") if seg != ""]


def _parse_segment(raw, line_no):
    if raw.startswith("*"):
        name = raw[1:]
        if not name:
            raise RouteError(line_no, "wildcard segment is missing a name")
        return ("wildcard", name, None)
    if raw.startswith(":"):
        body = raw[1:]
        name, sep, type_name = body.partition(":")
        if not sep:
            type_name = "str"
        if not name:
            raise RouteError(line_no, "named segment is missing a name")
        if type_name not in PARAM_TYPES:
            raise RouteError(line_no, f"unknown parameter type ':{type_name}' in '{raw}'")
        return ("param", name, type_name)
    return ("literal", raw, None)


def _parse_segments(raw_segments, line_no):
    segments = []
    seen_names = set()
    for i, raw in enumerate(raw_segments):
        kind, name, type_name = _parse_segment(raw, line_no)
        if kind == "wildcard" and i != len(raw_segments) - 1:
            raise RouteError(line_no, f"wildcard segment '{raw}' must be last")
        if kind in ("param", "wildcard"):
            if name in seen_names:
                raise RouteError(line_no, f"duplicate parameter name '{name}'")
            seen_names.add(name)
        segments.append((kind, name, type_name))
    return segments


def parse_routes(lines):
    routes = []
    for line_no, raw in enumerate(lines, start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        pattern = parts[0]
        name = parts[1].strip() if len(parts) > 1 else None
        if not pattern.startswith("/"):
            raise RouteError(line_no, f"pattern '{pattern}' must start with '/'")
        routes.append(Route(pattern, name, line_no))
    return routes


def find_matches(routes, path):
    path_segments = _split_path(path)
    results = []
    for route in routes:
        params = route.match(path_segments)
        if params is not None:
            results.append((route, params))
    return results


def _route_to_dict(route, params):
    return {
        "pattern": route.pattern,
        "name": route.name,
        "line": route.line_no,
        "params": params,
    }


def format_human(path, matches):
    if not matches:
        return f"no route matches {path!r}"
    winner_route, winner_params = matches[0]
    lines = [f"{path!r} matches {winner_route.pattern!r} (line {winner_route.line_no})"]
    if winner_route.name:
        lines.append(f"  name: {winner_route.name}")
    if winner_params:
        lines.append("  params:")
        for key, value in winner_params.items():
            lines.append(f"    {key} = {value!r}")
    else:
        lines.append("  params: none")
    if len(matches) > 1:
        lines.append(f"  also matched ({len(matches) - 1}, shadowed by the route above):")
        for route, params in matches[1:]:
            suffix = f" params={params}" if params else ""
            lines.append(f"    {route.pattern!r} (line {route.line_no}){suffix}")
    return "\n".join(lines)


def format_json(path, matches):
    payload = {
        "path": path,
        "matched": bool(matches),
        "route": _route_to_dict(*matches[0]) if matches else None,
        "shadowed": [_route_to_dict(r, p) for r, p in matches[1:]] if matches else [],
    }
    return json.dumps(payload, indent=2)


def format_route_list_human(routes):
    if not routes:
        return "no routes registered"
    width = max(len(route.pattern) for route in routes)
    lines = [f"{len(routes)} route(s):"]
    for route in routes:
        entry = f"  line {route.line_no:<4} {route.pattern:<{width}}"
        if route.name:
            entry += f"  {route.name}"
        lines.append(entry)
    return "\n".join(lines)


def format_route_list_json(routes):
    payload = {
        "routes": [
            {"line": route.line_no, "pattern": route.pattern, "name": route.name}
            for route in routes
        ]
    }
    return json.dumps(payload, indent=2)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="routematch",
        description="Find which route pattern matches a given path.",
    )
    parser.add_argument("routes_file", help="path to a file listing route patterns")
    parser.add_argument(
        "path", nargs="?", help="the URL path to test, e.g. /users/42 (omit with --list)"
    )
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON instead of text"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="dump all registered routes with their line numbers instead of matching a path",
    )
    args = parser.parse_args(argv)

    if not args.list and args.path is None:
        parser.error("the following arguments are required: path (unless --list is given)")

    try:
        with open(args.routes_file, "r", encoding="utf-8") as f:
            routes = parse_routes(f)
    except OSError as exc:
        print(f"routematch: cannot read {args.routes_file!r}: {exc.strerror}", file=sys.stderr)
        return 1
    except RouteError as exc:
        print(f"routematch: {args.routes_file}: {exc}", file=sys.stderr)
        return 1

    if args.list:
        if args.json:
            print(format_route_list_json(routes))
        else:
            print(format_route_list_human(routes))
        return 0 if routes else 1

    matches = find_matches(routes, args.path)

    if args.json:
        print(format_json(args.path, matches))
    else:
        print(format_human(args.path, matches))

    return 0 if matches else 1


if __name__ == "__main__":
    sys.exit(main())
