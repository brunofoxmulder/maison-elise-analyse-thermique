from app.compressor_regime import classify_compressor_frequency, compressor_regime_context


def test_compressor_regime_thresholds():
    assert classify_compressor_frequency(None) is None
    assert classify_compressor_frequency(0) == "très faible"
    assert classify_compressor_frequency(15) == "très faible"
    assert classify_compressor_frequency(15.1) == "faible"
    assert classify_compressor_frequency(22) == "faible"
    assert classify_compressor_frequency(22.1) == "moyen"
    assert classify_compressor_frequency(35) == "moyen"
    assert classify_compressor_frequency(35.1) == "fort"


def test_compressor_regime_context_is_descriptive_only():
    context = compressor_regime_context(15.2, 22.0)
    assert context["mean_regime_family"] == "faible"
    assert context["max_regime_family"] == "faible"
    assert context["thresholds_hz"] == {
        "très faible": "<=15",
        "faible": "16-22",
        "moyen": "23-35",
        "fort": ">35",
    }
    assert context["rule"] == "practical_reading_only_not_manufacturer_rating_not_power_conversion"
