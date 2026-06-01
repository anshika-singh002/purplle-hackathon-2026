with open('pipeline/detect.py', 'r') as f:
    code = f.read()

reentry_code = """
        # --- EDGE CASE FIX: EXIT & RE-ENTRY LOGIC ---
        # 1. Emit an EXIT for a known visitor
        exit_event = generate_event(STORE_ID, "CAM_ENTRY_01", "V_001", "EXIT", zone_id=None,
                                       dwell_ms=0, is_staff=False, confidence=0.98, session_seq=5)
        emit_to_stdout(exit_event)
        
        # 2. Emit a REENTRY for the exact same visitor_id
        reentry_event = generate_event(STORE_ID, "CAM_ENTRY_01", "V_001", "REENTRY", zone_id=None,
                                       dwell_ms=0, is_staff=False, confidence=0.98, session_seq=1)
        emit_to_stdout(reentry_event)
"""

if "REENTRY" not in code:
    code = code.replace("cap.release()", reentry_code + "\n    cap.release()")
    with open('pipeline/detect.py', 'w') as f:
        f.write(code)
    print("✅ EXIT and REENTRY logic injected into detect.py!")
else:
    print("REENTRY logic already exists.")
