from starlette.testclient import TestClient

from logos_copilot.web import app

c = TestClient(app)


def test_index_ok():
    r = c.get("/")
    assert r.status_code == 200 and "Logos Copilot" in r.text


def test_empty_query_400():
    assert c.get("/api/search?q=").status_code == 400
    assert c.get("/api/search?q=%20%20").status_code == 400


def test_non_dict_feedback_400():
    for body in ["null", "[1,2,3]", '"x"', "42", "true"]:
        r = c.post("/api/feedback", content=body, headers={"content-type": "application/json"})
        assert r.status_code == 400, f"{body} -> {r.status_code}"


def test_bad_rating_400():
    assert c.post("/api/feedback", json={"rating": "meh"}).status_code == 400


def test_oversized_body_413():
    big = '{"rating":"up","comment":"' + ("x" * 20000) + '"}'
    r = c.post("/api/feedback", content=big,
               headers={"content-type": "application/json", "content-length": str(len(big))})
    assert r.status_code == 413
