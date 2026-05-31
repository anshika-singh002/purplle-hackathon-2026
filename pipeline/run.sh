#!/bin/bash

echo "Starting Apex Retail Store Intelligence Pipeline..."

# Ensure output directory exists
mkdir -p output

# Clear previous runs
> output/events.jsonl

# Run the detection pipeline and append output to events.jsonl
# (In the final version, you would loop through CAM 1, CAM 2, etc. here)
echo "Processing CAM 1.mp4..."
python3 pipeline/detect.py >> output/events.jsonl

echo "Processing complete! All events saved to output/events.jsonl"
