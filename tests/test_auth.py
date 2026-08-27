from sync.yahoo_auth import (
    authorization_url,
    exchange_authorization_code,
    parse_token_response,
    refresh_yahoo_token,
    update_github_actions_secret,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self):
        self.calls = []
        self.responses = []

    def queue(self, response):
        self.responses.append(response)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)


def test_parse_token_response_keeps_old_refresh_token_when_absent():
    result = parse_token_response(
        {"access_token": "ACCESS", "expires_in": 3600},
        current_refresh_token="OLD_REFRESH",
    )
    assert result.access_token == "ACCESS"
    assert result.refresh_token == "OLD_REFRESH"
    assert result.rotated is False
    assert result.expires_in == 3600


def test_parse_token_response_detects_rotated_refresh_token():
    result = parse_token_response(
        {"access_token": "ACCESS", "refresh_token": "NEW_REFRESH", "expires_in": 3600},
        current_refresh_token="OLD_REFRESH",
    )
    assert result.refresh_token == "NEW_REFRESH"
    assert result.rotated is True


def test_refresh_yahoo_token_posts_expected_form_without_logging_tokens(capsys):
    session = FakeSession()
    session.queue(FakeResponse({"access_token": "ACCESS", "expires_in": 3600}))

    result = refresh_yahoo_token(
        client_id="CLIENT",
        client_secret="SECRET",
        refresh_token="REFRESH",
        session=session,
    )

    assert result.access_token == "ACCESS"
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url == "https://api.login.yahoo.com/oauth2/get_token"
    assert kwargs["auth"] == ("CLIENT", "SECRET")
    assert kwargs["data"] == {
        "grant_type": "refresh_token",
        "refresh_token": "REFRESH",
        "redirect_uri": "oob",
    }
    captured = capsys.readouterr()
    assert "ACCESS" not in captured.out + captured.err
    assert "REFRESH" not in captured.out + captured.err


def test_update_github_actions_secret_uses_stdin_not_command_line(capsys):
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return object()

    update_github_actions_secret(
        repository="jdnicely/cotr-yahoo-fantasy",
        github_token="GH_TOKEN_VALUE",
        secret_name="YAHOO_REFRESH_TOKEN",
        secret_value="NEW_REFRESH_VALUE",
        runner=fake_runner,
    )

    command, kwargs = calls[0]
    assert command == [
        "gh",
        "secret",
        "set",
        "YAHOO_REFRESH_TOKEN",
        "--repo",
        "jdnicely/cotr-yahoo-fantasy",
    ]
    assert "NEW_REFRESH_VALUE" not in " ".join(command)
    assert kwargs["input"] == "NEW_REFRESH_VALUE"
    assert kwargs["env"]["GH_TOKEN"] == "GH_TOKEN_VALUE"
    assert kwargs["check"] is True
    assert kwargs["text"] is True
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "NEW_REFRESH_VALUE" not in combined
    assert "GH_TOKEN_VALUE" not in combined


def test_authorization_url_uses_oob_code_flow_and_fantasy_read_scope():
    url = authorization_url("CLIENT")
    assert url.startswith("https://api.login.yahoo.com/oauth2/request_auth?")
    assert "client_id=CLIENT" in url
    assert "redirect_uri=oob" in url
    assert "response_type=code" in url
    assert "scope=fspt-r" in url
    assert "language=en-us" in url


def test_exchange_authorization_code_uses_same_redirect_uri():
    session = FakeSession()
    session.queue(FakeResponse({"access_token": "ACCESS", "refresh_token": "REFRESH", "expires_in": 3600}))

    result = exchange_authorization_code(
        client_id="CLIENT",
        client_secret="SECRET",
        code="CODE",
        session=session,
    )

    assert result.refresh_token == "REFRESH"
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url == "https://api.login.yahoo.com/oauth2/get_token"
    assert kwargs["auth"] == ("CLIENT", "SECRET")
    assert kwargs["data"] == {
        "grant_type": "authorization_code",
        "code": "CODE",
        "redirect_uri": "oob",
    }
