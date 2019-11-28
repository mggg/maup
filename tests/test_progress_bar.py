from maup.progress_bar import progress, with_progress
from tqdm import tqdm


def test_progress_enables_progress_bar():
    assert progress.enabled is False
    with progress:
        assert progress.enabled is True


def test_progress_is_callable():
    assert progress() is progress


def test_with_progress_wraps_with_tqdm_if_progress_is_enabled():
    def mock_generator():
        yield 1
        yield 2
        yield 3

    with progress:
        wrapped = with_progress(mock_generator())
        assert isinstance(wrapped, tqdm)

    gen = mock_generator()
    assert not isinstance(gen, tqdm)
