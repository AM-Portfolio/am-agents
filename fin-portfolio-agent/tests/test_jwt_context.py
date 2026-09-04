import base64
import json

from shared.context.jwt_context import jwt_subject, resolve_request_user_id, bearer_token


def _make_jwt(sub: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).decode().rstrip("=")
    return f"{header}.{payload}.sig"


def test_jwt_subject_extracts_sub():
    token = _make_jwt("user-abc-123")
    assert jwt_subject(token) == "user-abc-123"


def test_resolve_prefers_jwt_over_body():
    token = _make_jwt("jwt-user")
    uid, jwt_sub = resolve_request_user_id(
        body_user_id="",
        header_user_id=None,
        auth_header=f"Bearer {token}",
    )
    assert uid == "jwt-user"
    assert jwt_sub == "jwt-user"


def test_resolve_uses_body_when_no_jwt():
    uid, jwt_sub = resolve_request_user_id(
        body_user_id="body-user",
        header_user_id=None,
        auth_header="",
    )
    assert uid == "body-user"
    assert jwt_sub is None


def test_bearer_token_strips_prefix():
    assert bearer_token("Bearer abc.def.ghi") == "abc.def.ghi"
