import pytest
from maup.progress_bar import ProgressBar
from tqdm import tqdm


@pytest.fixture
def progress():
    return ProgressBar()


def test_progress_enables_progress_bar(progress):
    assert progress.enabled is False
    with progress:
        assert progress.enabled is True


def test_progress_is_callable(progress):
    assert progress() is progress


def test_with_progress_wraps_with_tqdm_if_progress_is_enabled(progress):
    def mock_generator():
        yield 1
        yield 2
        yield 3

    with progress:
        wrapped = progress(mock_generator())
        assert isinstance(wrapped, tqdm)

    gen = progress(mock_generator())
    assert not isinstance(gen, tqdm)


def test_the_user_can_activate_progress_bars_in_general(progress):
    def mock_generator():
        yield 1
        yield 2
        yield 3

    progress.enabled = True

    gen = progress(mock_generator)
    assert isinstance(gen, tqdm)
