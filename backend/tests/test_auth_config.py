"""REQ-36 (c): GET /api/auth/config tells the UI whether email and registration work.

Public, two booleans only; no secret, key or invite code in the response.
"""
import os
import sys

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402

SECRETS = {"REGISTRATION_INVITE_CODE": "invite-s3cr3t-value", "RESEND_API_KEY": "re_s3cr3t_key",
           "SENDGRID_API_KEY": "SG.s3cr3t", "SMTP_HOST": "smtp.example.com", "SMTP_USER": "mailer",
           "SMTP_PASSWORD": "smtp-s3cr3t"}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in SECRETS:
        monkeypatch.delenv(name, raising=False)


def _config():
    response = TestClient(app).get("/api/auth/config")  # no session cookie: public
    assert response.status_code == 200, response.text
    return response.json()


def test_nothing_configured():
    assert _config() == {"email_enabled": False, "registration_open": False}


@pytest.mark.parametrize("env, expected", [
    ({"REGISTRATION_INVITE_CODE": "invite-s3cr3t-value"}, {"email_enabled": False, "registration_open": True}),
    ({"REGISTRATION_INVITE_CODE": "   "}, {"email_enabled": False, "registration_open": False}),
    ({"RESEND_API_KEY": "re_s3cr3t_key"}, {"email_enabled": True, "registration_open": False}),
    ({"SENDGRID_API_KEY": "SG.s3cr3t"}, {"email_enabled": True, "registration_open": False}),
    ({"SMTP_HOST": "smtp.example.com", "SMTP_USER": "mailer", "SMTP_PASSWORD": "smtp-s3cr3t"},
     {"email_enabled": True, "registration_open": False}),
    ({"SMTP_HOST": "smtp.example.com"}, {"email_enabled": False, "registration_open": False}),  # incomplete SMTP
])
def test_each_setting(monkeypatch, env, expected):
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    assert _config() == expected


def test_no_secret_appears_in_the_response(monkeypatch):
    for name, value in SECRETS.items():
        monkeypatch.setenv(name, value)

    response = TestClient(app).get("/api/auth/config")

    assert response.json() == {"email_enabled": True, "registration_open": True}
    assert not any(value in response.text for value in SECRETS.values())
