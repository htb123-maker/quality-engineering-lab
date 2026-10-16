"""Brute-force protection on the password grant.

Week 5 covered token lifecycle: expiry, refresh rotation, revocation. Week 11
adds the credential-stuffing guard: repeated failures on one (client, account)
pair are counted in Redis and answered with 429 until the window drains, while a
successful sign-in clears the counter.
"""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import math

import allure
import httpx
import pytest
from qa_core.config.settings import Settings
from qa_core.http import HttpClient
from qa_core.resource_pools import NamespaceLease
from qa_core.security import SignInThrottleProbe, retry_after_seconds

from tests.api.conftest import attach_json, unique_client_id

WRONG_PASSWORD = "definitely-not-the-password"
UNKNOWN_EMAIL = "nobody@atlasexample.test"


def _password_grant(
    settings: Settings,
    *,
    email: str,
    password: str,
    client_id: str | None = None,
) -> httpx.Response:
    """Send one password grant without the SDK's retry and refresh logic."""

    headers = {"X-QA-Client-Id": client_id} if client_id else None
    with HttpClient.from_settings(settings) as client:
        return client.post(
            settings.auth_token_path,
            data={
                "grant_type": "password",
                "username": email,
                "password": password,
            },
            headers=headers,
        )


@allure.epic("Quality Engineering Lab")
@allure.feature("Authorization")
@allure.story("Sign-in throttle")
@pytest.mark.api
def test_repeated_failed_signins_trip_the_lockout(
    sut_api_url: str,
    settings: Settings,
    signin_throttle: SignInThrottleProbe,
) -> None:
    del sut_api_url

    client_id = unique_client_id("lockout")
    signin_throttle.clear(client_id=client_id, email=UNKNOWN_EMAIL)
    try:
        attempts = [
            _password_grant(
                settings,
                email=UNKNOWN_EMAIL,
                password=WRONG_PASSWORD,
                client_id=client_id,
            )
            for _ in range(settings.auth_signin_failure_max)
        ]
        blocked = _password_grant(
            settings,
            email=UNKNOWN_EMAIL,
            password=WRONG_PASSWORD,
            client_id=client_id,
        )
        failures = signin_throttle.failures(
            client_id=client_id,
            email=UNKNOWN_EMAIL,
        )
        ttl = signin_throttle.ttl_seconds(
            client_id=client_id,
            email=UNKNOWN_EMAIL,
        )
    finally:
        signin_throttle.clear(client_id=client_id, email=UNKNOWN_EMAIL)

    assert {attempt.status_code for attempt in attempts} == {400}
    assert {attempt.json()["error"] for attempt in attempts} == {"invalid_grant"}
    assert blocked.status_code == 429
    assert blocked.json()["error"] == "rate_limited"
    assert (retry_after_seconds(blocked) or 0) >= 1
    assert failures == settings.auth_signin_failure_max
    assert 0 < ttl <= math.ceil(settings.auth_signin_failure_window_seconds)
    attach_json(
        "Sign-in lockout",
        {
            "failures": failures,
            "counter_ttl_seconds": ttl,
            "retry_after": blocked.headers.get("Retry-After"),
            "body": blocked.json(),
        },
    )


@allure.feature("Authorization")
@allure.story("Sign-in throttle")
@pytest.mark.api
def test_a_successful_signin_clears_the_failure_counter(
    settings: Settings,
    namespace: NamespaceLease,
    signin_throttle: SignInThrottleProbe,
) -> None:
    client_id = unique_client_id("reset")
    email = namespace.owner_email
    signin_throttle.clear(client_id=client_id, email=email)
    try:
        for _ in range(settings.auth_signin_failure_max - 1):
            failed = _password_grant(
                settings,
                email=email,
                password=WRONG_PASSWORD,
                client_id=client_id,
            )
            assert failed.status_code == 400
        before = signin_throttle.failures(client_id=client_id, email=email)

        accepted = _password_grant(
            settings,
            email=email,
            password=settings.auth_test_password,
            client_id=client_id,
        )
        after = signin_throttle.failures(client_id=client_id, email=email)
    finally:
        signin_throttle.clear(client_id=client_id, email=email)

    assert before == settings.auth_signin_failure_max - 1
    assert accepted.status_code == 200
    assert after == 0
    attach_json(
        "Failure counter reset",
        {"before": before, "after": after, "status": accepted.status_code},
    )


@allure.feature("Authorization")
@allure.story("Sign-in throttle")
@pytest.mark.api
def test_lockout_is_scoped_to_one_account(
    settings: Settings,
    namespace: NamespaceLease,
    signin_throttle: SignInThrottleProbe,
) -> None:
    """One locked account must not lock the whole client."""

    client_id = unique_client_id("scoped-lockout")
    locked_email = namespace.owner_email
    signin_throttle.clear(client_id=client_id, email=locked_email)
    try:
        for _ in range(settings.auth_signin_failure_max):
            _password_grant(
                settings,
                email=locked_email,
                password=WRONG_PASSWORD,
                client_id=client_id,
            )
        locked = _password_grant(
            settings,
            email=locked_email,
            password=WRONG_PASSWORD,
            client_id=client_id,
        )
        other = _password_grant(
            settings,
            email=UNKNOWN_EMAIL,
            password=WRONG_PASSWORD,
            client_id=client_id,
        )
    finally:
        signin_throttle.clear(client_id=client_id, email=locked_email)

    assert locked.status_code == 429
    assert other.status_code == 400
    assert other.json()["error"] == "invalid_grant"
    attach_json(
        "Lockout scope",
        {"locked": locked.status_code, "other_account": other.status_code},
    )


@allure.feature("Authorization")
@allure.story("Sign-in throttle")
@pytest.mark.api
def test_other_endpoints_stay_usable_during_a_lockout(
    settings: Settings,
    namespace: NamespaceLease,
    signin_throttle: SignInThrottleProbe,
) -> None:
    """The throttle protects one grant, not the whole API surface."""

    client_id = unique_client_id("other-endpoints")
    email = namespace.owner_email
    signin_throttle.clear(client_id=client_id, email=email)
    try:
        for _ in range(settings.auth_signin_failure_max):
            _password_grant(
                settings,
                email=email,
                password=WRONG_PASSWORD,
                client_id=client_id,
            )
        blocked = _password_grant(
            settings,
            email=email,
            password=WRONG_PASSWORD,
            client_id=client_id,
        )
        with HttpClient.from_settings(settings) as client:
            health = client.get("/health/live")
            catalog = client.get(f"/api/v1/workspaces/{namespace.slug}/catalog")
    finally:
        signin_throttle.clear(client_id=client_id, email=email)

    assert blocked.status_code == 429
    assert health.status_code == 200
    assert catalog.status_code == 200
    attach_json(
        "Lockout containment",
        {"token": blocked.status_code, "health": 200, "catalog": 200},
    )
