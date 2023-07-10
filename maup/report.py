class Report:
    def __init__(self) -> None:
        pass

    def assign_to_max_error(self, pieces, max_area_idx):
        listy_idx = list(zip(max_area_idx.index, max_area_idx))
        self.discarded_pieces = pieces.drop(index=listy_idx)
        

    @classmethod
    def new_assign_report(cls, sources, targets):
        rprt = cls()
        rprt.sources = sources
        rprt.targets = targets

        return rprt