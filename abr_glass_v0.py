import os
import time
import subprocess
import keyboard
from datetime import datetime
import RPi.GPIO as GPIO

# Set up the button GPIO
BUTTON_GPIO = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Directory where the segment files are stored
SEGMENT_DIR = "/home/boazburnett/Videos"

# Start the FFmpeg command
ffmpeg_command = [
    "ffmpeg", "-f", "v4l2", "-video_size", "1280x720", "-thread_queue_size", "1024", "-i", "/dev/video0",
    "-f", "alsa", "-thread_queue_size", "1024", "-itsoffset", "1.0", "-i", "hw:2,0", "-preset", "ultrafast",
    "-r", "30", "-vf", "transpose=1,transpose=1", "-f", "segment", "-segment_time", "10", "-segment_format", "mkv",
    "output.mkv"
]
subprocess.Popen(ffmpeg_command)

# Function to handle button press
def button_pressed():
    # Get the current time and format it as a string
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    # Combine the segment files into one file
    with open(f"{timestamp}.mkv", "wb") as outfile:
        for i in range(6):
            filename = f"out{str(i).zfill(3)}.mkv"
            with open(os.path.join(SEGMENT_DIR, filename), "rb") as infile:
                outfile.write(infile.read())

# Set up the button press interrupt
GPIO.add_event_detect(BUTTON_GPIO, GPIO.FALLING, callback=button_pressed, bouncetime=300)

# Set up the keyboard press event
keyboard.on_press_key("r", lambda _: button_pressed())

# Main loop
try:
    while True:
        # Get a list of the segment files
        files = sorted(os.listdir(SEGMENT_DIR))

        # If there are more than 6 files, delete the oldest ones
        while len(files) > 6:
            os.remove(os.path.join(SEGMENT_DIR, files.pop(0)))

        time.sleep(1)
except KeyboardInterrupt:
    GPIO.cleanup()