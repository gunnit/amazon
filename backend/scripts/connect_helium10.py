"""Connect Inthezon to a Helium 10 account (one-time browser approval).

Registers Inthezon as an OAuth client of Helium 10's MCP server (dynamic
client registration, public client + PKCE), opens nothing by itself: it
prints an approval link. Open it in a browser signed in to the Helium 10
account, pick the account and press CONTINUE. The browser is sent back to
http://localhost:8765/callback on this machine, the code is exchanged, and the
tokens are written to --out (default ~/.inthezon/helium10_tokens.json, mode
0600). Token values are never printed.

Then set on the API service (Render):
    HELIUM10_CLIENT_ID      = client id printed below
    HELIUM10_REFRESH_TOKEN  = "refresh_token" from the --out file
The backend renews its ~18-minute access token from these by itself. Revoke
the approval any time from the Helium 10 account settings.

Usage:
    python scripts/connect_helium10.py [--out PATH]
"""
import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import urllib.parse
from pathlib import Path

import httpx

PORT = 8765
REDIRECT = f"http://localhost:{PORT}/callback"
RESOURCE = "https://mcp.helium10.com/mcp"
BASE = "https://members.helium10.com/authhub/api/scenarios/mcp"
REGISTER = f"{BASE}/connect/register"
AUTHORIZE = f"{BASE}/oauth2/authorize"
TOKEN = f"{BASE}/oauth2/token"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path.home() / ".inthezon" / "helium10_tokens.json"))
    out = Path(parser.parse_args().out).expanduser()

    registration = httpx.post(REGISTER, json={
        "client_name": "Inthezon Tool",
        "redirect_uris": [REDIRECT],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": "mcp:tools",
    }, timeout=30)
    if registration.status_code >= 400:
        print(f"Registration failed: {registration.status_code} {registration.text[:300]}")
        return 1
    client_id = registration.json()["client_id"]

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    link = AUTHORIZE + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "scope": "mcp:tools",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": RESOURCE,
    })
    print("Open this link in a browser signed in to Helium 10 and press CONTINUE:\n")
    print(link + "\n", flush=True)

    result: dict = {}
    done = threading.Event()

    class Callback(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            result.update({k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()})
            ok = "code" in result and result.get("state") == state
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            message = "Helium 10 collegato. Puoi chiudere questa scheda." if ok else "Autorizzazione non riuscita."
            self.wfile.write(f"<h2 style='font-family:sans-serif'>{message}</h2>".encode())
            done.set()

        def log_message(self, *args):  # keeps the code out of the console
            pass

    server = http.server.HTTPServer(("127.0.0.1", PORT), Callback)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if not done.wait(timeout=900):
        print("No approval within 15 minutes.")
        return 1
    server.shutdown()
    if result.get("state") != state or "code" not in result:
        print(f"Approval failed: {result.get('error', 'state mismatch')}")
        return 1

    tokens = httpx.post(TOKEN, data={
        "grant_type": "authorization_code",
        "code": result["code"],
        "redirect_uri": REDIRECT,
        "client_id": client_id,
        "code_verifier": verifier,
        "resource": RESOURCE,
    }, timeout=30)
    if tokens.status_code >= 400:
        print(f"Token exchange failed: {tokens.status_code}")
        return 1
    payload = tokens.json()
    payload["client_id"] = client_id
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    os.chmod(out, 0o600)
    print(f"Connected. Tokens saved to {out}")
    print(f"HELIUM10_CLIENT_ID={client_id}")
    print('HELIUM10_REFRESH_TOKEN=<the "refresh_token" value in that file>')
    return 0


if __name__ == "__main__":
    sys.exit(main())
