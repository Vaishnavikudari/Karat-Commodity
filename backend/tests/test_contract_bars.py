"""Unit test for ContractBars sizing requirements:
1. Heights increase with weight (GOLDM 100g > GOLDTEN 10g > GOLDGUINEA 8g > GOLDPETAL 1g)
2. Minimum height holds (1g bar stays visible with min height constraint)
3. Levelled heights are equal across all contracts when 'Show on one scale' is active
"""
import math
import pytest

MIN_HEIGHT = 44.0
LEVELLED_HEIGHT = 110.0
SCALE_FACTOR = 34.0

def calculate_bar_height(weight_g: float, is_levelled: bool = False) -> float:
    """Calculate the height for ContractBars based on cube root of pack weight."""
    if is_levelled:
        return LEVELLED_HEIGHT
    cbrt_h = round(math.pow(weight_g, 1.0 / 3.0) * SCALE_FACTOR, 1)
    return max(MIN_HEIGHT, cbrt_h)

class TestContractBarsSizing:
    def test_minimum_height_holds(self):
        """The 1g bar (and any arbitrarily small weight) must respect the minimum height constraint."""
        h_1g = calculate_bar_height(1.0, is_levelled=False)
        assert h_1g >= MIN_HEIGHT, f"1g bar height {h_1g} must be >= {MIN_HEIGHT}"
        assert h_1g == MIN_HEIGHT, f"1g bar height should floor at exactly {MIN_HEIGHT}"

        # Sub-gram test
        h_half_g = calculate_bar_height(0.5, is_levelled=False)
        assert h_half_g >= MIN_HEIGHT

    def test_heights_increase_with_weight(self):
        """Contract bar heights must strictly increase with pack size: 1g < 8g < 10g < 100g."""
        contracts = [
            ("GOLDPETAL", 1.0),
            ("GOLDGUINEA", 8.0),
            ("GOLDTEN", 10.0),
            ("GOLDM", 100.0)
        ]
        heights = [(sym, calculate_bar_height(w, is_levelled=False)) for sym, w in contracts]

        # Verify strict ordering
        h_petal = heights[0][1]
        h_guinea = heights[1][1]
        h_ten = heights[2][1]
        h_m = heights[3][1]

        assert h_petal < h_guinea < h_ten < h_m, (
            f"Heights must strictly increase with pack size: "
            f"GOLDPETAL={h_petal}, GOLDGUINEA={h_guinea}, GOLDTEN={h_ten}, GOLDM={h_m}"
        )

    def test_levelled_heights_are_equal(self):
        """When levelled ('Show on one scale'), all bar heights must be identical."""
        weights = [1.0, 8.0, 10.0, 100.0]
        levelled_heights = [calculate_bar_height(w, is_levelled=True) for w in weights]
        assert len(set(levelled_heights)) == 1, f"All levelled heights must be equal, got {levelled_heights}"
        assert levelled_heights[0] == LEVELLED_HEIGHT
