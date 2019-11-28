from tqdm import tqdm


class ProgressBar:
    def __init__(self):
        self.enabled = False
        self._previous_value = False

    def __call__(self, generator=None, total=None):
        """Add an optional progress bar to a generator. A tqdm progress bar
        will display if the `ProgressBar` is enabled.
        """
        if generator is None:
            return self
        if self.enabled:
            return tqdm(generator, total=total)
        return generator

    def __enter__(self):
        self._previous_value = self.enabled
        self.enabled = True

    def __exit__(self, *args):
        self.enabled = self._previous_value


progress = ProgressBar()
