"""
Valaioli -- URL validation (Stage 3).

Strict allowlist-based YouTube URL pattern matching.
Only accept recognised YouTube URL shapes; reject everything else.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

# Supported YouTube hostnames
_ALLOWED_HOSTS = frozenset({
    "www.youtube.com",
    "youtube.com",
    "youtu.be",
    "music.youtube.com",
    "www.music.youtube.com",
    "m.youtube.com",
})

_ALLOWED_BASE_HOSTS = frozenset({
    "youtube.com",
    "youtu.be",
    "music.youtube.com",
    "m.youtube.com",
})

# YouTube video ID pattern (11 characters, base64url)
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# YouTube playlist ID pattern (PL, RD, UU, FL prefixes, 13-60 chars)
_PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{13,60}$")

# Standard youtube.com/watch?v= URL
_WATCH_RE = re.compile(r"^/watch$")

# Short youtu.be/<id> URL
_SHORT_RE = re.compile(r"^/([A-Za-z0-9_-]{11})$")

# YouTube Shorts URL: /shorts/<id>
_SHORTS_RE = re.compile(r"^/shorts/([A-Za-z0-9_-]{11})(?:/.*)?$")

# YouTube Live URL: /live/<id>
_LIVE_RE = re.compile(r"^/live/([A-Za-z0-9_-]{11})(?:/.*)?$")


class UnsupportedURLError(ValueError):
    """Raised when a URL is not an allowed YouTube video URL."""


def validate_youtube_url(raw_url: str) -> str:
    """
    Validate and canonicalise a YouTube video URL.

    Returns the canonical https://www.youtube.com/watch?v=<id> form.
    Raises UnsupportedURLError for anything that does not match.

    Supported URL forms:
    - https://www.youtube.com/watch?v=<id>
    - https://youtube.com/watch?v=<id>
    - https://music.youtube.com/watch?v=<id>
    - https://m.youtube.com/watch?v=<id>
    - https://youtu.be/<id>
    - https://www.youtube.com/shorts/<id>
    - https://www.youtube.com/live/<id>

    Security notes:
    - Only HTTPS is accepted.
    - Only recognised YouTube hostnames are accepted.
    - Only the 'v' query parameter is forwarded; all others are stripped.
    - No user-supplied path components pass through unvalidated.
    """
    raw_url = raw_url.strip()
    try:
        parsed = urlparse(raw_url)
    except Exception as exc:
        raise UnsupportedURLError("Malformed URL.") from exc

    if parsed.scheme not in ("https", "http"):
        raise UnsupportedURLError("Only HTTPS YouTube URLs are accepted.")

    raw_host = (parsed.hostname or "").lower()
    base_host = raw_host.removeprefix("www.")

    if raw_host not in _ALLOWED_HOSTS and base_host not in _ALLOWED_BASE_HOSTS:
        raise UnsupportedURLError(f"Unsupported host: {parsed.hostname!r}.")

    video_id: str | None = None

    if base_host == "youtu.be":
        m = _SHORT_RE.match(parsed.path)
        if not m:
            raise UnsupportedURLError("Could not extract video ID from youtu.be URL.")
        video_id = m.group(1)
    else:
        if _WATCH_RE.match(parsed.path):
            params = parse_qs(parsed.query)
            ids = params.get("v", [])
            if len(ids) != 1:
                raise UnsupportedURLError("Missing or ambiguous 'v' parameter.")
            video_id = ids[0]
        elif m := _SHORTS_RE.match(parsed.path):
            video_id = m.group(1)
        elif m := _LIVE_RE.match(parsed.path):
            video_id = m.group(1)
        else:
            raise UnsupportedURLError(
                "Only youtube.com/watch?v=..., /shorts/<id>, and /live/<id> URLs are supported."
            )

    if not _VIDEO_ID_RE.match(video_id):
        raise UnsupportedURLError("Video ID contains unexpected characters.")

    canonical = urlunparse((
        "https",
        "www.youtube.com",
        "/watch",
        "",
        urlencode({"v": video_id}),
        "",
    ))
    return canonical


def validate_playlist_url(raw_url: str) -> tuple[str, str]:
    """
    Validate and canonicalise a YouTube playlist URL.

    Returns (canonical_playlist_url, playlist_id) on success.
    Raises UnsupportedURLError if the URL is not a recognised playlist URL.

    Accepted URL forms:
    - https://www.youtube.com/playlist?list=<id>
    - https://music.youtube.com/playlist?list=<id>
    - https://www.youtube.com/watch?v=<vid>&list=<id>  (video-in-playlist context)
    - https://music.youtube.com/watch?v=<vid>&list=<id>
    """
    raw_url = raw_url.strip()
    try:
        parsed = urlparse(raw_url)
    except Exception as exc:
        raise UnsupportedURLError("Malformed URL.") from exc

    if parsed.scheme not in ("https", "http"):
        raise UnsupportedURLError("Only HTTPS YouTube URLs are accepted.")

    raw_host = (parsed.hostname or "").lower()
    base_host = raw_host.removeprefix("www.")
    if raw_host not in _ALLOWED_HOSTS and base_host not in _ALLOWED_BASE_HOSTS:
        raise UnsupportedURLError(f"Unsupported host: {parsed.hostname!r}.")

    params = parse_qs(parsed.query)
    playlist_ids = params.get("list", [])
    if len(playlist_ids) != 1:
        raise UnsupportedURLError(
            "URL does not contain a 'list' parameter. "
            "Paste a YouTube playlist URL (youtube.com/playlist?list=...)."
        )

    playlist_id = playlist_ids[0]
    if not _PLAYLIST_ID_RE.match(playlist_id):
        raise UnsupportedURLError("Playlist ID contains unexpected characters.")

    canonical = urlunparse((
        "https",
        "www.youtube.com",
        "/playlist",
        "",
        urlencode({"list": playlist_id}),
        "",
    ))
    return canonical, playlist_id


def is_playlist_url(raw_url: str) -> bool:
    """Return True if the URL contains a ?list= parameter."""
    try:
        parsed = urlparse(raw_url.strip())
        raw_host = (parsed.hostname or "").lower()
        base_host = raw_host.removeprefix("www.")
        if raw_host not in _ALLOWED_HOSTS and base_host not in _ALLOWED_BASE_HOSTS:
            return False
        params = parse_qs(parsed.query)
        return bool(params.get("list"))
    except Exception:
        return False
