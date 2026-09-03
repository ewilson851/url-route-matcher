# routematch

Given a list of route patterns and a path, tell me which pattern actually
matches, what parameters it captures, and whether any other pattern in the
list would also have matched (and is therefore silently shadowed).

Every web framework has this router internally, but it's buried behind
the framework's request cycle, so the only way to answer "why did this
request go to that handler" is usually to add a print statement and fire
a real request. This does the same lookup as a standalone query against a
plain text file, no framework required.

## Usage

Write your routes to a text file, one pattern per line, in the order your
router registers them:

```
# routes.txt
/                      home
/users                 users.list
/users/:id             users.show
/users/:id/posts/:pid  users.post.show
/static/*path          static.serve
```

- A segment like `:id` matches exactly one path segment and captures it.
- A segment like `*path` must be the last one in the pattern and captures
  everything remaining, including slashes.
- Everything else has to match literally.
- Text after the pattern is an optional free-form name, purely for display.

Then query it:

```
$ python3 routematch.py routes.txt /users/42
'/users/42' matches '/users/:id' (line 3)
  name: users.show
  params:
    id = '42'
```

Ask for JSON when you want to script against the result:

```
$ python3 routematch.py routes.txt /users/42 --json
{
  "path": "/users/42",
  "matched": true,
  "route": {
    "pattern": "/users/:id",
    "name": "users.show",
    "line": 3,
    "params": {
      "id": "42"
    }
  },
  "shadowed": []
}
```

If a second pattern further down the file would also have matched, it
shows up under `shadowed` (or in the "also matched" section of the human
output) instead of silently vanishing. That's usually the interesting
case: two routes that look unambiguous on their own turn out to overlap.

No route matches:

```
$ python3 routematch.py routes.txt /does/not/exist
no route matches '/does/not/exist'
```

The process exits `0` when a route matched and `1` otherwise, so it's
usable in scripts and CI without the `--json` flag.

## Why not just read the framework's route table

Most frameworks expose *something* like `app.url_map` or `router.stack`,
but the format differs per framework and per version, and dumping it
still leaves you doing the segment matching by eye. This tool works off
one plain text format regardless of what generated it, so a route list
exported from Flask, Express, or a hand-rolled router can all be checked
the same way.

## Requirements

Python 3.8 or newer. No third-party dependencies.
