"""Response wrapper middleware.

Wraps all successful API JSON responses in a standard envelope::

    { "status": <http_code>, "success": true, "data": <original_body> }

Route handlers return the UNWRAPPED payload; this middleware adds the envelope.

Implementation note (carried over from sp-company-backend)
---------------------------------------------------------
The route handler has already serialized its payload to JSON bytes by the time
this middleware sees it. Parsing those bytes back into Python and re-dumping
them is a full parse + re-serialize of every byte the API returns, on the
event-loop thread. The envelope is a pure textual prefix/suffix, so it is
spliced onto the raw bytes instead::

    b'{"status":200,"success":true,"data":' + body + b'}'

That is byte-identical to the re-serialized form — Starlette's JSONResponse
emits compact JSON with separators ``(",", ":")`` — at a fraction of the cost.

The only thing that needed the parse was the "already an envelope" guard, which
is preserved and now reached only when the body *could* be an envelope:

* a body starting with ``[`` is a JSON array and can never be a dict carrying
  ``success``/``data``, so it is spliced with no parse;
* a body not literally containing both ``"success"`` and ``"data"`` cannot be a
  dict with both keys, so it too is spliced with no parse;
* anything else is parsed and the original guard applies.
"""

import json

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Substrings that MUST be present in the raw JSON of an already-wrapped
# envelope. Absence of either proves the body is not an envelope, which lets
# the middleware skip parsing it entirely.
_ENVELOPE_MARKERS = (b'"success"', b'"data"')

# Every byte a well-formed JSON document can begin with. Used as a cheap
# stand-in for "did this parse?" so a non-JSON body with a JSON content-type is
# still handed back untouched.
_JSON_START_BYTES = frozenset(
    (b"{", b"[", b'"', b"-", b"t", b"f", b"n", *(str(d).encode() for d in range(10)))
)


def _splice_envelope(body: bytes, status_code: int) -> bytes:
    """Wrap already-serialized JSON ``body`` in the standard envelope.

    Textual splice — no parse, no re-serialize.

    Args:
        body: Raw JSON bytes emitted by the route handler.
        status_code: HTTP status to record in the envelope.

    Returns:
        The enveloped JSON bytes.
    """
    return (
        b'{"status":'
        + str(status_code).encode("ascii")
        + b',"success":true,"data":'
        + body
        + b"}"
    )


class ResponseWrapperMiddleware(BaseHTTPMiddleware):
    """Wrap successful API responses in a standard envelope.

    Only wraps responses that:
    - Are for /api/ routes
    - Have a 2xx status code
    - Have application/json content type

    Usage::

        from src.shared.infrastructure.middleware import ResponseWrapperMiddleware

        app.add_middleware(ResponseWrapperMiddleware)
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process the request and wrap successful JSON API responses."""
        response = await call_next(request)

        if not request.url.path.startswith("/api/"):
            return response

        if response.status_code >= 400:
            return response

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        body_chunks: list[bytes] = []
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            if isinstance(chunk, str):
                body_chunks.append(chunk.encode("utf-8"))
            else:
                body_chunks.append(chunk)
        body = b"".join(body_chunks)

        stripped = body.lstrip()
        # A body that does not even start like JSON is handed back untouched.
        # (An empty body falls through here too.)
        if stripped[0:1] not in _JSON_START_BYTES:
            return response

        # Fast path: an array, or an object that cannot possibly carry both
        # envelope keys, needs no parse at all.
        is_array = stripped[0:1] == b"["
        may_be_envelope = not is_array and all(
            marker in body for marker in _ENVELOPE_MARKERS
        )

        if may_be_envelope:
            try:
                original = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return response

            # Don't double-wrap if already in envelope format
            if (
                isinstance(original, dict)
                and "success" in original
                and "data" in original
            ):
                return response

        wrapped = _splice_envelope(body, response.status_code)

        # Drop content-length (recalculated from the spliced body) and
        # content-type (re-set below).
        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in ("content-length", "content-type")
        }

        return Response(
            content=wrapped,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
        )
