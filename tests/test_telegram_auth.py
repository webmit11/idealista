import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from app.services.telegram_auth import validate_init_data

TOKEN = "123456:TEST-TOKEN"


def _make_init_data(token=TOKEN, user_id=42, auth_date=None):
    auth_date = auth_date if auth_date is not None else int(time.time())
    pairs = {
        "auth_date": str(auth_date),
        "query_id": "AAAA",
        "user": json.dumps({"id": user_id, "first_name": "T"}),
    }
    dcs = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


def test_valid_init_data():
    d = validate_init_data(_make_init_data(user_id=7), TOKEN)
    assert d is not None and d["user"]["id"] == 7


def test_wrong_token_rejected():
    assert validate_init_data(_make_init_data(), "999:WRONG") is None


def test_tampered_hash_rejected():
    data = _make_init_data()
    assert validate_init_data(data + "0", TOKEN) is None  # extra param breaks the hash


def test_stale_rejected():
    assert validate_init_data(_make_init_data(auth_date=1), TOKEN) is None


def test_empty_rejected():
    assert validate_init_data("", TOKEN) is None
    assert validate_init_data(_make_init_data(), "") is None
