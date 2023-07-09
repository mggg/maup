class Report:
    def __init__(self) -> None:
        pass

    @classmethod
    def new_assign_report(cls, sources, targets):
        rprt = cls()
        rprt.sources = sources
        rprt.targets = targets

        return rprt