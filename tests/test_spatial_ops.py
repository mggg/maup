from spatial_ops import Refinement


def test_refinement_can_be_created_from_a_dataframe(four_square_grid):
    refinement = Refinement(four_square_grid)
    assert refinement
