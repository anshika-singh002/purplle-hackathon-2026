# 🏢 Apex Retail: Store Intelligence System

## 🔗 Setup & Execution (Exactly 5 Commands)

Follow these commands to clone, deploy, process video, and view the real-time analytics dashboard:

1. `git clone https://github.com/anshika-singh002/purplle-hackathon-2026.git`
2. `cd purplle-hackathon-2026`
3. `docker compose up -d --build`
4. `./pipeline/run.sh`
5. `curl http://localhost:8000/stores/STORE_BLR_002/metrics`

*(Note: The `pipeline/run.sh` command processes the clips and routes output to `output/events.jsonl` before ingesting it automatically into the API).*

## 📊 Live Interactive Dashboard

The frontend has been upgraded to a React-style Single Page Application (SPA) featuring tabbed navigation, live metrics polling, conversion funnels, floor heatmaps, and active anomaly alerts.

As per the specification, the local dashboard can be accessed at: 
[http://localhost:8000/dashboard](http://localhost:8000/dashboard)


## 🎤 Pitch Presentation

View the full project pitch deck here:

[Apex Retail Intelligence - Pitch Deck](https://drive.google.com/file/d/1f_OggoRbZI2K0UeSzi2N9MgbbJ0-fQv4/view?usp=sharing)

