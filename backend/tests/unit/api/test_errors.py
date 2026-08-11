from shuttlecube.api.errors import ConcurrentChange


def test_concurrent_change_is_problem_409() -> None:
    error = ConcurrentChange()
    assert error.status == 409
    assert error.code == "concurrent_change"
