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

# Ensure the segment directory exists
os.makedirs(SEGMENT_DIR, exist_ok=True)

# Function to start recording
def start_recording():
    global ffmpeg_process
    
    # Clear any existing segments
    for file in os.listdir(SEGMENT_DIR):
        os.remove(os.path.join(SEGMENT_DIR, file))
    
    # Start the FFmpeg command
    ffmpeg_command = [
        "ffmpeg",
        "-f", "v4l2",
        "-video_size", "1280x720",
        "-thread_queue_size", "1024",
        "-i", "/dev/video0",
        "-f", "alsa",
        "-thread_queue_size", "1024",
        "-channels", "1",  # Force mono audio input
        "-sample_rate", "44100",  # Use a supported sample rate
        "-itsoffset", "1.0",
        "-i", "hw:5,0",
        "-preset", "veryfast",
        "-ac", "1",  # Force mono audio output
        "-ar", "44100",  # Set audio rate for output
        "-r", "30",
        "-vf", "transpose=1,transpose=1",
        "-f", "segment",
        "-segment_time", "10",
        "-segment_format", "mkv",
        os.path.join(SEGMENT_DIR, "output%03d.mkv")
    ]
    
    print("Starting recording...")
    ffmpeg_process = subprocess.Popen(ffmpeg_command)

def combine_and_exit():
    global ffmpeg_process
    
    print("Stopping recording...")
    # Stop the FFmpeg process
    if ffmpeg_process:
        ffmpeg_process.terminate()
        ffmpeg_process.wait()
    
    print("Waiting for files to be finalized...")
    time.sleep(1)  # Give a bit of time for files to be fully written
    
    # Get the current time and format it as a string
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    
    # Get a list of the segment files, sorted by creation time
    files = sorted(os.listdir(SEGMENT_DIR), key=lambda x: os.path.getctime(os.path.join(SEGMENT_DIR, x)))
    
    # Make sure we have at least 2 files
    if len(files) < 2:
        print(f"Not enough segment files found. Only found {len(files)} files.")
        GPIO.cleanup()
        return
    
    # Take only the first two segments
    segments = files[0:2]
    
    print(f"Combining segments: {segments}")
    
    # Check if all the necessary files exist and are accessible
    for segment in segments:
        path = os.path.join(SEGMENT_DIR, segment)
        if not os.path.exists(path):
            print(f"File {path} does not exist.")
            GPIO.cleanup()
            return
        if not os.access(path, os.R_OK):
            print(f"File {path} is not accessible.")
            GPIO.cleanup()
            return
    
    # Create a temporary file that contains the list of files to concatenate
    with open("temp.txt", "w") as f:
        for segment in segments:
            path = os.path.join(SEGMENT_DIR, segment)
            f.write(f"file '{path}'\n")
    
    output_file = f"{timestamp}.mkv"
    print(f"Creating output file: {output_file}")
    
    # Create an FFmpeg command to concatenate the segment files
    ffmpeg_concat_command = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", "temp.txt",
        output_file
    ]
    
    # Run the FFmpeg command
    process = subprocess.Popen(ffmpeg_concat_command)
    process.wait()
    
    # Delete the temporary file
    os.remove("temp.txt")
    
    print(f"Recording complete: {output_file}")
    GPIO.cleanup()
    exit()

# Set up the button press interrupt
GPIO.add_event_detect(BUTTON_GPIO, GPIO.FALLING, callback=lambda x: combine_and_exit(), bouncetime=300)

# Set up the keyboard press event
keyboard.on_press_key("r", lambda *args: combine_and_exit())

# Main function
def main():
    try:
        # Start recording immediately
        start_recording()
        
        print("Recording started. Press the button or 'r' key to finish after two 10-second segments.")
        
        # Wait for just over 20 seconds (two 10-second segments)
        time.sleep(21)
        
        # Automatically combine and exit after recording two segments
        combine_and_exit()
            
    except KeyboardInterrupt:
        if ffmpeg_process:
            ffmpeg_process.terminate()
        GPIO.cleanup()
        print("Recording canceled by user.")

if __name__ == "__main__":
    main()