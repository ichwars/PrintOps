"""Small escaped, uncached pages for narrowly scoped notification actions."""

from html import escape

from fastapi import Request
from fastapi.responses import HTMLResponse

from backend.app.models.print_log import PrintLogEntry


def confirmation_page(request: Request, run: PrintLogEntry, verdict: str, *, saved: bool = False) -> HTMLResponse:
    answered = run.good_quantity is not None
    name = escape(run.print_name or "Print outcome")
    label = "Good parts" if verdict == "good" else "Rejected parts"
    body = f"<p>{name}</p>"
    if saved or answered:
        heading = "Saved" if saved else "Already answered"
        body += f"<p>Good: {run.good_quantity}; rejected: {run.reject_quantity}.</p>"
        body += "<p>You can correct this inspection in PrintOps.</p>"
    else:
        heading = "Confirm production quality"
        body += f"<p>Record all {run.quantity} intended parts as {label.lower()}?</p>"
        body += "<p>For a partial rejection, open this print in PrintOps and enter the quantities.</p>"
        body += "<form method='post' id='confirmation'><button type='submit'>Confirm</button></form>"
        # Only direct notification buttons carry tap=1. Text links and unattended
        # scanners never submit a form; a GET itself is always read-only.
        agent = request.headers.get("user-agent", "").lower()
        unattended = any(
            word in agent
            for word in ("bot", "crawler", "spider", "preview", "safelinks", "proofpoint", "mimecast", "urldefense")
        )
        unattended |= any(
            any(word in request.headers.get(header, "").lower() for word in ("prefetch", "preview"))
            for header in ("purpose", "sec-purpose", "x-purpose", "x-moz")
        )
        nonce = getattr(request.state, "csp_nonce", None)
        if nonce and request.query_params.get("tap") == "1" and not unattended:
            body += f"<script nonce='{escape(nonce, quote=True)}'>document.getElementById('confirmation').submit();</script>"
    html = "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>PrintOps</title></head>"
    html += f"<body style='font-family:system-ui;padding:2rem;max-width:32rem;margin:auto'><h1>{heading}</h1>{body}</body></html>"
    return HTMLResponse(
        html,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex, nofollow"},
    )
