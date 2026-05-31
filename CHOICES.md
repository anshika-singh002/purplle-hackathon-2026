# Technical Choices & Rationale

## 1. Detection Model Choice
**Options considered:** YOLOv8, YOLOv11, OpenCV Background Subtraction, MediaPipe.
**What AI suggested:** The AI initially suggested YOLOv8 as it is highly stable and widely documented for tracking.
**What I chose and why:** I chose **YOLOv11n (Nano) paired with ByteTrack**. While YOLOv8 is great, I needed this pipeline to run locally on an Apple Silicon Mac without extreme thermal throttling. YOLOv11n offers superior inference speeds while maintaining enough accuracy to generate stable bounding boxes. ByteTrack was chosen over DeepSORT because it relies heavily on spatial positioning rather than deep appearance features, making it significantly faster for edge processing.

## 2. Event Schema Design Rationale
**Options considered:** Deeply nested JSON metadata vs. Flat structured tables.
**What AI suggested:** The AI suggested separating the schema strictly into "Core" fields and deeply nesting everything else (queue depth, staff flags, confidence) into a flexible `metadata` dictionary.
**What I chose and why:** I compromised between the Apex Retail API requirements and a flat structure. I utilized Pydantic to strictly type the core fields (`event_id`, `visitor_id`, `timestamp`), but I kept `is_staff` and `confidence` at the root level rather than burying them in metadata. This choice makes the downstream SQLite database much easier to query. If we had nested them deeply, calculating metrics like "Unique visitors (exclude is_staff=true)" would require complex JSON-extraction queries in SQLite, which slows down the `/metrics` endpoint.

## 3. API Architecture (Where I Disagreed with AI)
**Options considered:** Writing a custom Excel parser vs. Mathematical Mock Zones.
**What AI suggested:** When we realized the `store_layout` was provided as a visual `.xlsx` file (a colored-in grid map) instead of a JSON coordinates file, **the AI suggested using `openpyxl` to extract cell background colors to map the floorplan into coordinates.**
**What I chose and why:** **I completely disagreed and overrode this.** I chose to implement a mathematical mock-zone generator (e.g., `if y > 800: return 'ENTRY'`) inside the pipeline instead. Writing a custom script to parse Excel background colors is brittle, highly error-prone, and a massive time-sink for a 24-hour hackathon. My goal was to prove the system architecture worked end-to-end (Event Ingestion -> Database -> Analytics). By mocking the geometry, I kept the pipeline moving and successfully completed the API metrics logic. Swapping to real polygons later is simply a one-line function update, proving that the architecture is modular and resilient.
