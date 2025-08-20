import random
import geopandas
import maup
import pytest
from shapely.geometry import Point, Polygon

from maup import assign, doctor
from maup.adjacencies import adjacencies
from maup.smart_repair import smart_repair


@pytest.fixture
def toy_precincts_geoseries():
    random.seed(2023)
    ppolys = []
    for i in range(4):
        for j in range(4):
            poly = Polygon(
                [
                    (0.5 * i + 0.1 * k, 0.5 * j + (random.random() - 0.5) / 12)
                    for k in range(6)
                ]
                + [
                    (0.5 * (i + 1) + (random.random() - 0.5) / 12, 0.5 * j + 0.1 * k)
                    for k in range(1, 6)
                ]
                + [
                    (
                        0.5 * (i + 1) - 0.1 * k,
                        0.5 * (j + 1) + (random.random() - 0.5) / 12,
                    )
                    for k in range(1, 6)
                ]
                + [
                    (0.5 * i + (random.random() - 0.5) / 12, 0.5 * (j + 1) - 0.1 * k)
                    for k in range(1, 5)
                ]
            )
            ppolys.append(poly)

    return geopandas.GeoSeries(ppolys)


@pytest.fixture
def toy_precincts_geodataframe():
    random.seed(2023)
    ppolys = []
    for i in range(4):
        for j in range(4):
            poly = Polygon(
                [
                    (0.5 * i + 0.1 * k, 0.5 * j + (random.random() - 0.5) / 12)
                    for k in range(6)
                ]
                + [
                    (0.5 * (i + 1) + (random.random() - 0.5) / 12, 0.5 * j + 0.1 * k)
                    for k in range(1, 6)
                ]
                + [
                    (
                        0.5 * (i + 1) - 0.1 * k,
                        0.5 * (j + 1) + (random.random() - 0.5) / 12,
                    )
                    for k in range(1, 6)
                ]
                + [
                    (0.5 * i + (random.random() - 0.5) / 12, 0.5 * (j + 1) - 0.1 * k)
                    for k in range(1, 5)
                ]
            )
            ppolys.append(poly)

    return geopandas.GeoDataFrame(geometry=geopandas.GeoSeries(ppolys))


@pytest.fixture
def toy_counties_geodataframe():
    cpoly1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    cpoly2 = Polygon([(1, 0), (2, 0), (2, 1), (1, 1)])
    cpoly3 = Polygon([(0, 1), (1, 1), (1, 2), (0, 2)])
    cpoly4 = Polygon([(1, 1), (2, 1), (2, 2), (1, 2)])

    return geopandas.GeoDataFrame(
        geometry=geopandas.GeoSeries([cpoly1, cpoly2, cpoly3, cpoly4])
    )


class TestSmartRepair:
    def test_smart_repair_basic_output_from_gdf_clean(self, toy_precincts_geodataframe):
        repaired_gdf = smart_repair(toy_precincts_geodataframe)
        assert isinstance(repaired_gdf, geopandas.GeoDataFrame)
        assert doctor(repaired_gdf)

    def test_smart_repair_basic_output_from_gs_clean(self, toy_precincts_geoseries):
        repaired_gs = smart_repair(toy_precincts_geoseries)
        assert isinstance(repaired_gs, geopandas.GeoSeries)
        assert doctor(repaired_gs)

    def test_nest_within_regions(
        self, toy_precincts_geodataframe, toy_counties_geodataframe
    ):
        repaired_with_regions_gdf = smart_repair(
            toy_precincts_geodataframe, nest_within_regions=toy_counties_geodataframe
        )
        p_to_c = assign(toy_precincts_geodataframe, toy_counties_geodataframe)
        for p in p_to_c.index:
            assert toy_counties_geodataframe.geometry[p_to_c[p]].contains(
                repaired_with_regions_gdf.geometry[p]
            )

    def test_small_rook_to_queen(self, toy_precincts_geodataframe):
        repaired_basic_gdf = smart_repair(toy_precincts_geodataframe)
        assert min(adjacencies(repaired_basic_gdf).length) < 0.05

        repaired_srtq_gdf = smart_repair(
            toy_precincts_geodataframe, min_rook_length=0.05
        )
        assert min(adjacencies(repaired_srtq_gdf).length) > 0.05


# There should also be a lot of unit tests for all the component functions,
# but this could mushroom into a BIG project that will have to wait for another day!
