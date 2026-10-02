"""
Property 25: API Response Envelope Consistency
Feature: verifiable-counterfactual-recourse, Property 25

Validates: Requirements 13.2, 13.3, 13.4, 13.5

For any response produced by success_response() or error_response():
  - success responses contain top-level "data" and NO top-level "error"
  - error responses contain top-level "error" (with "code" and "message") and NO top-level "data"
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.response import error_response, success_response


@given(
    data=st.one_of(
        st.none(),
        st.booleans(),
        st.integers(),
        st.text(max_size=200),
        st.dictionaries(st.text(max_size=20), st.integers(), max_size=10),
        st.lists(st.integers(), max_size=10),
    ),
    status_code=st.integers(min_value=200, max_value=299),
)
@settings(max_examples=100)
def test_success_response_has_data_not_error(data: object, status_code: int) -> None:
    """Success responses must contain 'data' and must NOT contain 'error'."""
    response = success_response(data, status_code=status_code)
    body = json.loads(response.body)

    assert "data" in body, "success_response must include top-level 'data' key"
    assert "error" not in body, "success_response must NOT include top-level 'error' key"
    assert response.status_code == status_code


@given(
    code=st.text(min_size=1, max_size=50),
    message=st.text(min_size=1, max_size=200),
    status_code=st.integers(min_value=400, max_value=599),
)
@settings(max_examples=100)
def test_error_response_has_error_not_data(code: str, message: str, status_code: int) -> None:
    """Error responses must contain 'error' with 'code'+'message' and must NOT contain 'data'."""
    response = error_response(code=code, message=message, status_code=status_code)
    body = json.loads(response.body)

    assert "error" in body, "error_response must include top-level 'error' key"
    assert "data" not in body, "error_response must NOT include top-level 'data' key"
    assert "code" in body["error"], "error envelope must contain 'code'"
    assert "message" in body["error"], "error envelope must contain 'message'"
    assert body["error"]["code"] == code
    assert body["error"]["message"] == message
    assert response.status_code == status_code


def test_success_and_error_never_share_keys() -> None:
    """The same response object must never have both 'data' and 'error' at the top level."""
    s = json.loads(success_response({"result": 1}).body)
    e = json.loads(error_response("TEST", "test error", 400).body)

    # Mutual exclusivity
    assert set(s.keys()).isdisjoint({"error"})
    assert set(e.keys()).isdisjoint({"data"})
