from geo_builder.colors import _hue_to_hex, _offsets, layer_color


class TestHueToHex:
    def test_blue(self):
        assert _hue_to_hex(240) == "#0000ff"

    def test_red(self):
        assert _hue_to_hex(0) == "#ff0000"

    def test_green(self):
        assert _hue_to_hex(120) == "#00ff00"

    def test_yellow(self):
        assert _hue_to_hex(60) == "#ffff00"

    def test_cyan(self):
        assert _hue_to_hex(180) == "#00ffff"

    def test_magenta(self):
        assert _hue_to_hex(300) == "#ff00ff"

    def test_wraps_360(self):
        assert _hue_to_hex(360) == _hue_to_hex(0)


class TestOffsets:
    def test_first_offset_is_zero(self):
        gen = _offsets(120)
        assert next(gen) == 0

    def test_second_offset_is_half_step(self):
        gen = _offsets(120)
        next(gen)
        assert next(gen) == 60

    def test_no_duplicate_offsets(self):
        gen = _offsets(120)
        seen = [next(gen) for _ in range(16)]
        assert len(seen) == len(set(seen))

    def test_all_offsets_within_step(self):
        gen = _offsets(120)
        for _ in range(16):
            assert 0 <= next(gen) < 120


class TestLayerColor:
    def test_index_0_is_blue(self):
        assert layer_color(0) == "#0000ff"

    def test_index_1_is_red(self):
        assert layer_color(1) == "#ff0000"

    def test_index_2_is_green(self):
        assert layer_color(2) == "#00ff00"

    def test_index_3_is_magenta(self):
        assert layer_color(3) == "#ff00ff"

    def test_index_4_is_yellow(self):
        assert layer_color(4) == "#ffff00"

    def test_index_5_is_cyan(self):
        assert layer_color(5) == "#00ffff"

    def test_all_colors_are_unique(self):
        colors = [layer_color(i) for i in range(12)]
        assert len(colors) == len(set(colors))

    def test_returns_hex_string(self):
        assert layer_color(0).startswith("#")
        assert len(layer_color(0)) == 7
