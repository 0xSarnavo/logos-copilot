import pytest

from logos_copilot.feedback import submit_feedback


def test_bad_rating_raises():
    # rating is validated before any DB use, so conn=None is fine
    with pytest.raises(ValueError):
        submit_feedback(None, query="x", rating="sideways")
    with pytest.raises(ValueError):
        submit_feedback(None, query="x", rating="")
