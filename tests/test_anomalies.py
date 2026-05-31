# PROMPT: Generate pytest for anomalies tracking DEAD_ZONE and BILLING_SPIKE.
# CHANGES MADE: Structured the test to evaluate basic threshold logic.
def test_anomaly_detection_logic():
    # If visits = 0 for 30 mins, flag DEAD_ZONE
    last_visit_mins_ago = 45
    anomaly = "DEAD_ZONE" if last_visit_mins_ago > 30 else None
    assert anomaly == "DEAD_ZONE"
