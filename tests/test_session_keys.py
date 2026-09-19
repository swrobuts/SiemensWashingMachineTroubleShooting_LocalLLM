from session_keys import SessionKeys


def test_key_expiry_and_isolation():
    now = [0]
    keys = SessionKeys(ttl=10, clock=lambda:now[0])
    keys.put("a","key-a")
    keys.put("b","key-b")
    assert keys.get("a") == "key-a"
    keys.remove("a")
    assert keys.get("a") is None
    assert keys.get("b") == "key-b"
    now[0] = 11
    assert keys.get("b") is None
