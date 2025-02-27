import os
import time
import subprocess
import keyboard
from datetime import datetime
import RPi.GPIO as GPIO
import sys

# Set up the button GPIO
BUTTON_GPIO = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Directory for segments
SEGMENT_DIR = "/home/boazburnett/projects/abr-glass/ABR_Glass_V0/segments"

# FFmpeg command
ffmpeg_command = [
    "ffmpeg",
    "-f", "v4l2",
    "-video_size", "1280x720",
    "-thread_queue_size", "1024",
    "-i", "/dev/video0",
    "-f", "alsa",
    "-thread_queue_size", "1024",
    "-channels", "1",
    "-sample_rate", "44100",
    "-itsoffset", "1.0",
    "-i", "hw:5,0",
    "-preset", "veryfast",
    "-ac", "1",
    "-ar", "44100",
    "-r", "30",
    "-vf", "transpose=1,transpose=1",
    "-f", "segment",
    "-segment_time", "10",
    "-segment_format", "mkv",
    os.path.join(SEGMENT_DIR, "output%03d.mkv")
]

def clear_segments():
    for file in os.listdir(SEGMENT_DIR):
        os.remove(os.path.join(SEGMENT_DIR, file))

def button_pressed():
    clear_segments()
    ffmpeg_process = subprocess.Popen(ffmpeg_command)
    while not os.path.exists(os.path.join(SEGMENT_DIR, "output001.mkv")):
        time.sleep(1)
    ffmpeg_process.terminate()
    ffmpeg_process.wait()
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    with open("temp.txt", "w") as f:
        f.write(f"file '{os.path.join(SEGMENT_DIR, 'output000.mkv')}'\n")
        f.write(f"file '{os.path.join(SEGMENT_DIR, 'output001.mkv')}'\n")
    ffmpeg_concat_command = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", "temp.txt", f"{timestamp}.mkv"]
    subprocess.run(ffmpeg_concat_command)
    os.remove("temp.txt")
    sys.exit(0)

# Set up event triggers
GPIO.add_event_detect(BUTTON_GPIO, GPIO.FALLING, callback=button_pressed, bouncetime=300)
keyboard.on_press_key("r", lambda _: button_pressed())

# Main loop
try:
    while True:
        time.sleep(1)
finally:
    GPIO.cleanup()