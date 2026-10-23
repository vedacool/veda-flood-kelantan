"""Shared settings: one place for flags, Malaysia time, Postgres address and secret patterns.

Everything that used to be copied between modules (audit 2026-10-22, P3 duplication) lives here.
"""
import os
import re
from datetime import timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MYT = timezone(timedelta(hours=8))   # Malaysia time, no DST - used for every human-facing time

PG_HOST = "127.0.0.1"           # not "localhost": Windows tries IPv6 ::1 first and veda-pg listens on IPv4 only
PG_PORT = 5433                       # veda-pg is published on 127.0.0.1:5433 only
PG_DB = "veda"


def flag(name, default=False):
    """True when env var `name` is 'true' (case/space-insensitive)."""
    return os.getenv(name, "true" if default else "false").strip().lower() == "true"


def sample_mode():
    """SAMPLE_MODE=true: offline judge mode, no live calls."""
    return flag("SAMPLE_MODE")


# --- Secrets -------------------------------------------------------------------------------------------------
# Env vars whose VALUES are secrets. Only VEDA's own keys - other tools' keys on the machine (e.g. *_API_KEY of
# unrelated apps) are not ours to mask and caused over-redaction of normal text.
SECRET_ENV_PREFIXES = ("METERLESS_", "ZETARIS_", "VEDA_", "NVIDIA_", "PG")
SECRET_ENV_KEY = re.compile(r"(TOKEN|KEY|PASSWORD|SECRET)")


def secret_env_values(environ=None, min_len=8):
    """[(key, value)] of VEDA secret env values worth masking / scanning for."""
    env = os.environ if environ is None else environ
    return [(k, v.strip()) for k, v in env.items()
            if k.startswith(SECRET_ENV_PREFIXES) and SECRET_ENV_KEY.search(k) and len(v.strip()) >= min_len]


# --- Flood replays (B-70) -------------------------------------------------------------------------------------
# A replay always says its title at the top of the answer (Husaini 22 Oct night). default_at = the first scene.
REPLAYS = {"nov2024": {"title": "REPLAY · Nov 2024", "default_at": "2024-11-26 18:00",
                       "window": ("2024-11-26 08:00", "2024-11-27 19:30"),     # first and last verified reading
                       "scenes": ["2024-11-26 18:00", "2024-11-27 08:00", "2024-11-27 19:30"]}}


# --- Personal data (B-56: no personal data in traces) --------------------------------------------------------
# Malaysian phone numbers and MyKad (IC) numbers typed into a question are masked in every trace line. Boundaries
# (no letter/digit/_/. on either side) keep gauge ids (5521044_DKKI0014), run ids, timestamps and coordinates intact.
_EDGE_L, _EDGE_R = r"(?<![\w.])", r"(?!\w|\.\d)"         # a full stop ending a sentence is fine
PERSONAL_PATTERNS = {
    "[phone]": re.compile(_EDGE_L + r"(?:\+?60[\s.-]?|0)(?:1\d|[3-9])[\s.-]?\d{3,4}[\s.-]?\d{4}" + _EDGE_R),
    "[IC]": re.compile(_EDGE_L + r"(?:\d{6}[\s-]\d{2}[\s-]\d{4}|\d{12})" + _EDGE_R),
    "[email]": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),      # audit 23 Oct: spaces / dots / emails
}


# Each pattern marks the secret part as group "secret" (redaction keeps the text around it). Placeholders such as
# "{PW}", "<token>", "$VAR", "***" and "…" are not secrets, so values must contain a letter/digit and none of {}<>$*.
_VAL = r"(?=[^\"'\s]*[A-Za-z0-9])[^\"'{}<>$*()\[\]\s]"   # code like os.environ["X"] is not a value
SECRET_PATTERNS = {
    "NVIDIA API key": re.compile(r"(?P<secret>nvapi-[A-Za-z0-9_\-]{8,})"),
    "OpenAI-style key": re.compile(r"(?P<secret>\bsk-[A-Za-z0-9_\-]{16,})"),
    "Bearer token": re.compile(r"(?i)\bBearer\s+(?P<secret>[A-Za-z0-9._~+/\-]{8,}=*)"),
    "Basic auth": re.compile(r"(?i)\bBasic\s+(?P<secret>[A-Za-z0-9+/]{12,}=*)"),
    "URL credentials": re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s:/@]+:(?P<secret>[^\s@/{}<>$*]{3,})@"),
    "private key": re.compile(r"(?P<secret>-----BEGIN [A-Z ]*PRIVATE KEY-----)"),
    "quoted password/token": re.compile(
        r"(?i)\b(?:password|passwd|pwd|secret|token|api[_-]?key|apikey)[\"']?\s*(?:[=:]\s*|\s+)[\"']"
        r"(?P<secret>" + _VAL + r"[^\"'{}<>$*]{2,})[\"']"),
    "secret env assignment": re.compile(
        r"\b[A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY)[A-Z0-9_]*=(?P<secret>" + _VAL + r"{7,})"
        r"(?![\w.\[(])"),            # a value followed by . [ ( is code (os.environ[...]), not a secret
    "secret key=value": re.compile(
        r"(?i)\b(?:password|passwd|secret|token|api[_-]?key)=(?P<secret>" + _VAL + r"{5,})(?![\w.\[(])"),
}
