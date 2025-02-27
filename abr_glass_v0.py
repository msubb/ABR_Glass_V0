import os
import time
import subprocess
import keyboard
from datetime import datetime
import RPi.GPIO as GPIO

ffmpeg_process = None  # Global variable to store the FFmpeg process

# Set up the button GPIO
BUTTON_GPIO = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Directory where the segment files are stored
SEGMENT_DIR = "/home/boazburnett/projects/abr-glass/ABR_Glass_V0/segments"

# Start the FFmpeg command
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
    os.path.join("/home/boazburnett/projects/abr-glass/ABR_Glass_V0/segments", "output%03d.mkv")
]

ffmpeg_process = subprocess.Popen(ffmpeg_command)

def button_pressed():
    global ffmpeg_process
    # Stop the FFmpeg process
    ffmpeg_process.terminate()
    ffmpeg_process.wait()

    # Get the current time and format it as a string
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    # Get a list of the segment files, sorted by creation time
    files = sorted(os.listdir(SEGMENT_DIR), key=lambda x: os.path.getctime(os.path.join(SEGMENT_DIR, x)))

    # Create a list of the six oldest segment files
    segments = files[0:6]  # Skip the newest file

    # Check if all the necessary files exist and are accessible
    for segment in segments:
        path = os.path.join(SEGMENT_DIR, segment)
        if not os.path.exists(path):
            print(f"File {path} does not exist.")
            return
        if not os.access(path, os.R_OK):
            print(f"File {path} is not accessible.")
            return

    # Create a temporary file that contains the list of files to concatenate
    with open("temp.txt", "w") as f:
        for segment in segments:
            path = os.path.join(SEGMENT_DIR, segment)
            f.write(f"file '{path}'\n")

    # Create an FFmpeg command to concatenate the segment files
    ffmpeg_concat_command = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", "temp.txt", f"{timestamp}.mkv"]
    # Run the FFmpeg command
    process = subprocess.Popen(ffmpeg_concat_command)
    process.wait()

    # Delete the temporary file
    os.remove("temp.txt")

    # Restart the FFmpeg process
    ffmpeg_process = subprocess.Popen(ffmpeg_command)

# Set up the button press interrupt
GPIO.add_event_detect(BUTTON_GPIO, GPIO.FALLING, callback=button_pressed, bouncetime=300)

# Set up the keyboard press event
keyboard.on_press_key("r", lambda _: button_pressed())

# Main loop
try:
    while True:
        # Get a list of the segment files
        files = sorted(os.listdir(SEGMENT_DIR), key=lambda x: os.path.getctime(os.path.join(SEGMENT_DIR, x)))

        # If there are more than 7 files, delete the oldest ones
        while len(files) > 7:
            os.remove(os.path.join(SEGMENT_DIR, files.pop(0)))

        time.sleep(1)
except KeyboardInterrupt:
    GPIO.cleanup()