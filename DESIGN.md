# Architecture & Design Overview

## Plain-Language Pipeline Description
The system is divided into an Edge Computer Vision pipeline and a Cloud/Server Intelligence API. 
1. **The Edge (Video Processing):** We feed CCTV `.mp4` files into a lightweight YOLOv11 tracker. As visitors move, a Python-based State Machine evaluates their bounding box coordinates against predefined store zones (Entry, Skincare, Billing). When a threshold is crossed (e.g., dwelling for 30s), the State Machine formats the event into a strict JSON schema and appends it to a local `events.jsonl` file.
2. **The Cloud (Intelligence API):** A FastAPI server accepts POST requests containing batches of these JSON events. It validates them using Pydantic, checks for duplicates, and ingests them into a local SQLite database. 
3. **The Brain (Metrics):** When a user requests `/stores/{id}/metrics`, the API executes SQL queries joining the YOLO events with the loaded POS transactions to calculate real-time funnel drop-offs and queue abandonment.

## AI-Assisted Decisions
During this hackathon, I utilized LLMs (primarily acting as a pair-programmer) to accelerate boilerplate generation and debug edge cases. 

* **State Machine Logic:** I used AI to help structure the `detect.py` state machine memory. Keeping track of active sessions across frames can get messy, so the AI suggested using a dictionary keyed by `visitor_id` containing sequence counters and zone-entry timestamps. I agreed with this approach as it kept time-complexity to O(1) for lookups.
* **Idempotency Implementation:** When designing the `/ingest` endpoint, I needed a way to satisfy the idempotency requirement. The AI suggested using SQLite's `INSERT OR REPLACE INTO` syntax. I agreed, as it completely eliminated the need for complex `SELECT` checks before every insert, saving significant processing time.

## VLM (Vision Language Model) Usage
I utilized a VLM strictly for debugging my workspace environment. When my terminal failed to locate `store_layout.json`, I took a screenshot of my macOS file explorer and uploaded it with the prompt: *"can you see it"*. The VLM successfully analyzed the image and identified that the organizers had provided an Excel file (`Brigade Road - Store layoutc5f5d56.xlsx`) instead of the expected JSON file. This saved me from wasting hours searching for a missing file. I did not use VLMs for zone classification in the video itself, as bounding-box math is much faster and cheaper for edge devices.
