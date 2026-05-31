# 🏬 Apex Retail: Store Intelligence System

## Setup & Execution (Exactly 5 Commands)
Follow these commands to clone, deploy, process video, and view the real-time analytics dashboard:

1. `git clone https://github.com/YOUR-USERNAME/purplle-hackathon-2026.git`
2. `cd purplle-hackathon-2026`
3. `docker compose up -d --build`
4. `./pipeline/run.sh`
5. `curl http://localhost:8000/stores/STORE_BLR_002/metrics`

*(Note: The `pipeline/run.sh` command processes the clips and routes output to `output/events.jsonl` before ingesting it automatically into the API).*

## 📊 Live Bonus Dashboard
To view the real-time Server-Sent Events (SSE) dashboard, open your browser and navigate to:
**[http://localhost:8000/dashboard](http://localhost:8000/dashboard)**
