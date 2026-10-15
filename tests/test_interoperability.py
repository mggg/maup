import geopandas
import pytest
from shapely.geometry import box

import maup


@pytest.fixture
def assigned_units():
    units = geopandas.GeoDataFrame(
        {"population": [10, 20]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs=5070,
    )
    districts = geopandas.GeoSeries([box(0, 0, 2, 1)], index=["A"], crs=5070)
    units["district"] = maup.assign(units, districts)
    assert units["district"].tolist() == ["A", "A"]
    return units


def test_assignment_to_gerrychain(assigned_units):
    gerrychain = pytest.importorskip("gerrychain")
    graph = gerrychain.Graph.from_geodataframe(assigned_units)
    partition = gerrychain.Partition(
        graph,
        assignment=assigned_units["district"].to_dict(),
        updaters={"population": gerrychain.updaters.Tally("population")},
    )
    assert set(partition.parts["A"]) == {0, 1}
    assert partition["population"] == {"A": 30}


def test_assignment_to_legacy_gerrytools(assigned_units, monkeypatch):
    geometry = pytest.importorskip("gerrytools.geometry")
    graph = geometry.dualgraph(assigned_units)
    assert graph.nodes[0]["district"] == "A"
    assert set(graph.edges) == {(0, 1)}

    assigned_units["unit"] = ["u", "v"]
    districts = geopandas.GeoDataFrame(
        {"district": ["A"]}, geometry=[box(0, 0, 2, 1)], crs=5070
    )
    monkeypatch.setattr(maup.progress, "enabled", False)
    assert geometry.unitmap((assigned_units, "unit"), (districts, "district")) == {
        "u": "A",
        "v": "A",
    }


def test_assignment_to_current_gerrytools(assigned_units):
    comparison = pytest.importorskip("gerrytools.plan_comparison")
    assigned_units["reference"] = ["B", "C"]
    overlap = comparison.population_overlap(
        assigned_units, source="district", target="reference", population="population"
    )
    assert overlap.loc["A"].to_dict() == {"B": 10, "C": 20}
