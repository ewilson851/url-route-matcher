import unittest

from routematch import (
    RouteError,
    find_matches,
    parse_routes,
)


class SegmentMatchingTests(unittest.TestCase):
    def test_literal_segments_match_exactly(self):
        routes = parse_routes(["/users/active"])
        matches = find_matches(routes, "/users/active")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][1], {})

    def test_literal_segment_rejects_different_value(self):
        routes = parse_routes(["/users/active"])
        self.assertEqual(find_matches(routes, "/users/inactive"), [])

    def test_named_segment_captures_value(self):
        routes = parse_routes(["/users/:id"])
        matches = find_matches(routes, "/users/42")
        self.assertEqual(matches[0][1], {"id": "42"})

    def test_named_segment_does_not_cross_slash(self):
        routes = parse_routes(["/users/:id"])
        self.assertEqual(find_matches(routes, "/users/42/posts"), [])

    def test_multiple_named_segments(self):
        routes = parse_routes(["/users/:id/posts/:pid"])
        matches = find_matches(routes, "/users/7/posts/99")
        self.assertEqual(matches[0][1], {"id": "7", "pid": "99"})

    def test_wildcard_captures_remaining_slashes(self):
        routes = parse_routes(["/static/*path"])
        matches = find_matches(routes, "/static/js/app.min.js")
        self.assertEqual(matches[0][1], {"path": "js/app.min.js"})

    def test_wildcard_requires_at_least_one_segment(self):
        routes = parse_routes(["/static/*path"])
        self.assertEqual(find_matches(routes, "/static"), [])

    def test_root_pattern_matches_only_root(self):
        routes = parse_routes(["/"])
        self.assertEqual(len(find_matches(routes, "/")), 1)
        self.assertEqual(find_matches(routes, "/anything"), [])

    def test_shorter_path_does_not_match_longer_pattern(self):
        routes = parse_routes(["/users/:id/posts"])
        self.assertEqual(find_matches(routes, "/users/42"), [])

    def test_longer_path_does_not_match_shorter_pattern(self):
        routes = parse_routes(["/users"])
        self.assertEqual(find_matches(routes, "/users/42"), [])


class AmbiguityDetectionTests(unittest.TestCase):
    def test_first_registered_wins(self):
        routes = parse_routes(
            [
                "/users/:id  users.show",
                "/users/active  users.active",
            ]
        )
        matches = find_matches(routes, "/users/active")
        self.assertEqual(len(matches), 2)
        winner, params = matches[0]
        self.assertEqual(winner.name, "users.show")
        self.assertEqual(params, {"id": "active"})

    def test_shadowed_route_is_reported_after_winner(self):
        routes = parse_routes(
            [
                "/users/:id  users.show",
                "/users/active  users.active",
            ]
        )
        matches = find_matches(routes, "/users/active")
        shadowed_route, shadowed_params = matches[1]
        self.assertEqual(shadowed_route.name, "users.active")
        self.assertEqual(shadowed_params, {})

    def test_non_overlapping_routes_report_single_match(self):
        routes = parse_routes(
            [
                "/users/:id  users.show",
                "/posts/:id  posts.show",
            ]
        )
        matches = find_matches(routes, "/users/42")
        self.assertEqual(len(matches), 1)

    def test_wildcard_can_be_shadowed_by_earlier_wildcard(self):
        routes = parse_routes(
            [
                "/static/*path  static.serve",
                "/static/*other  static.other",
            ]
        )
        matches = find_matches(routes, "/static/js/app.js")
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0][0].name, "static.serve")
        self.assertEqual(matches[1][0].name, "static.other")


class ParseValidationTests(unittest.TestCase):
    def test_blank_and_comment_lines_are_ignored(self):
        routes = parse_routes(["", "# just a comment", "/users  users.list"])
        self.assertEqual(len(routes), 1)

    def test_pattern_must_start_with_slash(self):
        with self.assertRaises(RouteError):
            parse_routes(["users  users.list"])

    def test_wildcard_must_be_last_segment(self):
        with self.assertRaises(RouteError):
            parse_routes(["/*rest/more"])

    def test_duplicate_parameter_names_are_rejected(self):
        with self.assertRaises(RouteError):
            parse_routes(["/users/:id/friends/:id"])

    def test_unnamed_wildcard_is_rejected(self):
        with self.assertRaises(RouteError):
            parse_routes(["/static/*"])

    def test_unnamed_param_is_rejected(self):
        with self.assertRaises(RouteError):
            parse_routes(["/users/:"])

    def test_trailing_name_is_captured(self):
        routes = parse_routes(["/users/:id  users.show"])
        self.assertEqual(routes[0].name, "users.show")

    def test_missing_name_is_none(self):
        routes = parse_routes(["/users/:id"])
        self.assertIsNone(routes[0].name)


if __name__ == "__main__":
    unittest.main()
