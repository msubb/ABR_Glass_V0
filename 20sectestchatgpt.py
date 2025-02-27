import os
import time
import subprocess
from datetime import datetime

# Directory where the segment files are stored
SEGMENT_DIR = "/home/boazburnett/projects/abr-glass/ABR_Glass_V0/segments"

# FFmpeg command to record and segment into 10 second clips
ffmpeg_command = [
    "ffmpeg",
    "-f", "v4l2", 
    "-video_size", "1280x720", 
    "-thread_queue_size", "1024", 
    "-i", "/dev/video0",
    "-f", "alsa", 
    "-thread_queue_size", "1024",
    "-channels", "1",         # Force mono audio input
    "-sample_rate", "44100",  # Use a supported sample rate
    "-itsoffset", "1.0", 
    "-i", "hw:5,0",
    "-preset", "veryfast",
    "-ac", "1",              # Force mono audio output
    "-ar", "44100",          # Set audio rate for output
    "-r", "30", 
    "-vf", "transpose=1,transpose=1",
    "-f", "segment", 
    "-segment_time", "10", 
    "-segment_format", "mkv",
    os.path.join(SEGMENT_DIR, "output%03d.mkv")
]

# Start FFmpeg segmentation
ffmpeg_process = subprocess.Popen(ffmpeg_command)
print("Recording 2 segments (approx. 20 seconds)...")

# Wait a little over 20 seconds to ensure two segments are recorded
time.sleep(21)

# Terminate the FFmpeg process
ffmpeg_process.terminate()
ffmpeg_process.wait()
print("Recording finished.")

# Get a timestamp for the output filename
now = datetime.now()
timestamp = now.strftime("%Y%m%d_%H%M%S")

# Retrieve the segment files and sort them by creation time
files = sorted(os.listdir(SEGMENT_DIR), key=lambda x: os.path.getctime(os.path.join(SEGMENT_DIR, x)))

# Use only the first two segments
segments = files[:2]

# Verify that both segment files exist and are readable
for segment in segments:
    path = os.path.join(SEGMENT_DIR, segment)
    if not os.path.exists(path):
        print(f"File {path} does not exist.")
        exit(1)
    if not os.access(path, os.R_OK):
        print(f"File {path} is not accessible.")
        exit(1)

# Create a temporary file listing the segment files to concatenate
temp_file = "temp.txt"
with open(temp_file, "w") as f:
    for segment in segments:
        path = os.path.join(SEGMENT_DIR, segment)
        f.write(f"file '{path}'\n")

# Build the FFmpeg command to concatenate the two segments
ffmpeg_concat_command = [
    "ffmpeg", "-f", "concat", "-safe", "0", "-i", temp_file, f"{timestamp}.mkv"
]

print("Combining segments...")
process = subprocess.Popen(ffmpeg_concat_command)
process.wait()

# Clean up the temporary file
os.remove(temp_file)

print(f"Combined video saved as {timestamp}.mkv")
