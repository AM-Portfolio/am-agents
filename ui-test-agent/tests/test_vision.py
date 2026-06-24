from app.vision.analyzer import vision_analyzer


def test_parse_bounding_box():
    box = vision_analyzer.parse_bounding_box("[100, 200, 300, 400]")
    assert box == [100, 200, 300, 400]


def test_translate_normalized_box():
    point = vision_analyzer.translate_normalized_box([0, 0, 1000, 1000], 1280, 800)
    assert point["x"] == 640
    assert point["y"] == 400
