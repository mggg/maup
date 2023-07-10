import pandas
from .report import Report
from .indexed_geometries import IndexedGeometries
from .intersections import intersections
from .crs import require_same_crs


@require_same_crs
def assign(sources, targets, return_report=False):
    """Assign source geometries to targets. A source is assigned to the
    target that covers it, or, if no target covers the entire source, the
    target that covers the most of its area.
    """
    assign_report = None
    if return_report: assign_report = Report.new_assign_report(sources, targets)
    
    assignment = pandas.Series(
        assign_by_covering(sources, targets),
        dtype="float"
    )
    assignment.name = None
    unassigned = sources[assignment.isna()]

    if return_report: assign_report.fully_covered_sources = sources[~assignment.isna()]

    if len(unassigned):  # skip if done
        assignments_by_area = pandas.Series(
            assign_by_area(unassigned, targets, assign_report),
            dtype="float"
        )
        assignment.update(assignments_by_area)

    if not return_report:
        return assignment.astype(targets.index.dtype, errors="ignore")
    else:
        return (assignment.astype(targets.index.dtype, errors="ignore"), assign_report)


def assign_by_covering(sources, targets):
    indexed_sources = IndexedGeometries(sources)
    return indexed_sources.assign(targets)


def assign_by_area(sources, targets, report=None):
    pieces = intersections(sources, targets, area_cutoff=0)
    max_area_idx = assign_to_max(pieces.area)

    if report is not None: report.assign_to_max_error(pieces, max_area_idx)
    return max_area_idx


def assign_to_max(weights):
    return weights.groupby(level="source").idxmax().apply(drop_source_label)


def drop_source_label(index):
    return index[1]
