import requests
import sys

BASE_URL = "http://localhost:8000"
STORE_ID = "STORE_BLR_002"
passed = 0
failed = 0

def assert_test(name, condition, error_msg=""):
    global passed, failed
    if condition:
        print(f"✅ PASS: {name}")
        passed += 1
    else:
        print(f"❌ FAIL: {name} - {error_msg}")
        failed += 1

print("\n--- 🚀 RUNNING APEX RETAIL FINAL ASSERTIONS ---\n")

try:
    # 1. Health Check
    res = requests.get(f"{BASE_URL}/health")
    assert_test("API Health Endpoint", res.status_code == 200 and res.json().get("status") == "healthy")

    # 2. Metrics Endpoint Structure
    res = requests.get(f"{BASE_URL}/stores/{STORE_ID}/metrics")
    data = res.json()
    assert_test("Metrics Returns 200 OK", res.status_code == 200)
    assert_test("Metrics Contains Unique Visitors", "unique_visitors" in data)
    assert_test("Metrics Has Real Data (Not Zero)", data.get("unique_visitors", 0) > 0, "No visitors found. Did ingest fail?")

    # 3. Funnel Endpoint
    res = requests.get(f"{BASE_URL}/stores/{STORE_ID}/funnel")
    funnel_data = res.json()
    assert_test("Funnel Returns 200 OK", res.status_code == 200)
    assert_test("Funnel Calculates Drop-offs", "drop_off_percentages" in funnel_data)

    # 4. Anomalies Endpoint
    res = requests.get(f"{BASE_URL}/stores/{STORE_ID}/anomalies")
    assert_test("Anomalies Returns 200 OK", res.status_code == 200)
    assert_test("Anomalies Output is List", isinstance(res.json().get("anomalies"), list))

    # 5. Idempotency Check (The most important one!)
    initial_visitors = data.get("unique_visitors", 0)
    
    # Resend the exact same sample data
    with open("output/events_array.json", "r") as f:
        payload = f.read()
    requests.post(f"{BASE_URL}/events/ingest", data=payload, headers={"Content-Type": "application/json"})
    
    # Fetch metrics again
    res_after = requests.get(f"{BASE_URL}/stores/{STORE_ID}/metrics")
    after_visitors = res_after.json().get("unique_visitors", 0)
    
    assert_test("Idempotency Maintained", initial_visitors == after_visitors, f"Visitors changed from {initial_visitors} to {after_visitors} after re-ingest!")
    
    # 6. Heatmap Endpoint
    res = requests.get(f"{BASE_URL}/stores/{STORE_ID}/heatmap")
    assert_test("Heatmap Returns 200 OK", res.status_code == 200)

except Exception as e:
    print(f"\n⚠️ CRITICAL ERROR DURING TESTS: {e}")

print(f"\n--- 🏁 TEST RESULTS: {passed} PASSED | {failed} FAILED ---\n")
if failed == 0:
    print("🏆 ALL ASSERTIONS PASSED! YOU ARE READY TO SUBMIT! 🏆\n")
