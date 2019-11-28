from tqdm import tqdm


class ProgressBar:
    def __init__(self):
        self.enabled = False

    def __call__(self):
        return self

    def __enter__(self):
        self.enabled = True

    def __exit__(self, *args):
        self.enabled = False


progress = ProgressBar()


def with_progress(generator, total=None):
    if progress.enabled:
        return tqdm(generator, total=total)
    return generator
