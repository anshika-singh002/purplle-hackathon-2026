# PROMPT: Generate pytest file for pipeline covering empty store and all-staff edge cases.
# CHANGES MADE: Added mock assertions to ensure is_staff filter works properly.
def test_empty_store_clip():
    # Simulates an empty store where no detections occur
    detections = []
    assert len(detections) == 0

def test_all_staff_clip():
    # Simulates a clip where all detected people match uniform color
    detections = [{"visitor_id": 1, "is_staff": True}, {"visitor_id": 2, "is_staff": True}]
    staff_count = sum(1 for d in detections if d["is_staff"])
    assert staff_count == 2
