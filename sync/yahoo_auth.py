from __future__ import annotations

import argparse
import getpass
import os
import subprocess
from urllib.parse import urlencode
from dataclasses import dataclass
from typing import Any, Callable

import requests

YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"


@dataclass(frozen=True)
class TokenResult:
    access_token: str
    refresh_token: str
    rotated: bool
    expires_in: int


def parse_token_response(payload: dict[str, Any], current_refresh_token: str) -> TokenResult:
    access_token = payload.get("access_token")
    if not access_token:
        raise ValueError("Yahoo token response did not include an access token")
    refresh_token = payload.get("refresh_token") or current_refresh_token
    if not refresh_token:
        raise ValueError("Yahoo token response did not include a usable refresh token")
    return TokenResult(
        access_token=str(access_token),
        refresh_token=str(refresh_token),
        rotated=str(refresh_token) != str(current_refresh_token),
        expires_in=int(payload.get("expires_in") or 3600),
    )


def refresh_yahoo_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    redirect_uri: str = "oob",
    session: requests.Session | Any | None = None,
) -> TokenResult:
    http = session or requests.Session()
    response = http.post(
        YAHOO_TOKEN_URL,
        auth=(client_id, client_secret),
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    response.raise_for_status()
    return parse_token_response(response.json(), current_refresh_token=refresh_token)


def update_github_actions_secret(
    repository: str,
    github_token: str,
    secret_name: str,
    secret_value: str,
    runner: Callable[..., Any] | None = None,
) -> None:
    if not repository or "/" not in repository:
        raise ValueError("repository must be in OWNER/REPO form")
    if not github_token:
        raise ValueError("github_token is required")
    run = runner or subprocess.run
    env = os.environ.copy()
    env["GH_TOKEN"] = github_token
    run(
        ["gh", "secret", "set", secret_name, "--repo", repository],
        input=secret_value,
        check=True,
        text=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def authorization_url(
    client_id: str,
    redirect_uri: str = "oob",
    scope: str = "fspt-r",
) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "language": "en-us",
        }
    )
    return f"https://api.login.yahoo.com/oauth2/request_auth?{query}"


def exchange_authorization_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str = "oob",
    session: requests.Session | Any | None = None,
) -> TokenResult:
    http = session or requests.Session()
    response = http.post(
        YAHOO_TOKEN_URL,
        auth=(client_id, client_secret),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    refresh = payload.get("refresh_token")
    access = payload.get("access_token")
    if not refresh or not access:
        raise ValueError("Yahoo authorization-code response did not include access and refresh tokens")
    return TokenResult(
        access_token=str(access),
        refresh_token=str(refresh),
        rotated=True,
        expires_in=int(payload.get("expires_in") or 3600),
    )


def bootstrap() -> int:
    client_id = os.environ.get("YAHOO_CLIENT_ID") or input("Yahoo Client ID: ").strip()
    client_secret = os.environ.get("YAHOO_CLIENT_SECRET") or getpass.getpass("Yahoo Client Secret: ")
    print("\nOpen this URL in your browser and authorize Fantasy Sports read access:\n")
    print(authorization_url(client_id))
    code = input("\nPaste the Yahoo authorization code: ").strip()
    token = exchange_authorization_code(client_id, client_secret, code)
    print("\nAuthorization succeeded. Add the following value directly as the")
    print("GitHub Actions secret YAHOO_REFRESH_TOKEN. Do not save it in this repo.\n")
    print(token.refresh_token)
    return 0


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Yahoo OAuth helpers for COTR fantasy sync")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("bootstrap", help="complete one-time Yahoo OAuth authorization")
    args = parser.parse_args(argv)
    if args.command == "bootstrap":
        return bootstrap()
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(cli())
