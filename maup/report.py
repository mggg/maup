class Report:
    def __init__(self) -> None:
        pass

    def assign_to_max_error(self, pieces, max_area_idx):
        listy_idx = list(zip(max_area_idx.index, max_area_idx))
        self.discarded_pieces = pieces.drop(index=listy_idx)
        self.discarded_area   = self.discarded_pieces.area.groupby(level="source").sum()/self.sources.area

    def __str__(self):
        if self.maup_method == 'assign':
            return(
                f'Assigned {len(self.sources)} source geometries to {len(self.targets)} target geometries\n'
                f'{len(self.fully_covered_sources)} source geometries perfectly nest\n'
                f'Of the remaining {len(self.sources) - len(self.fully_covered_sources)} source geometries:\n'
                f' • {len(self.discarded_area[self.discarded_area <= 0.005])} are >99.5% covered by one target geom.\n'
                f' • {len(self.discarded_area[(self.discarded_area <= 0.1) & (self.discarded_area > 0.005)])} are 90% -- 99.5% covered\n'
                f' • {len(self.discarded_area[self.discarded_area > 0.1])} are <90% covered\n'
                f' • {len(self.unassigned_sources)} are unassigned' 
            )
    

    @classmethod
    def new_assign_report(cls, sources, targets):
        rprt = cls()
        rprt.maup_method = "assign"
        rprt.sources = sources
        rprt.targets = targets
        rprt.fully_covered_sources = None
        rprt.discarded_pieces      = None
        rprt.discarded_area        = None
        rprt.unassigned_sources    = None

        return rprt