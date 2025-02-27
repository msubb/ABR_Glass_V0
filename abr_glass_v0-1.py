import os
import time
import subprocess
import keyboard
from datetime import datetime
import RPi.GPIO as GPIO
import threading

ffmpeg_process = None  # Global variable to store the FFmpeg process
segment_count = 0      # Counter for segment files
start_time = None      # Track when recording started

# Set up the button GPIO
BUTTON_GPIO = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Directory where the segment files are stored
SEGMENT_DIR = "/home/boazburnett/projects/abr-glass/ABR_Glass_V0/segments"

# Create segments directory if it doesn't exist
os.makedirs(SEGMENT_DIR, exist_ok=True)

# Updated FFmpeg command with correct audio parameters and more verbose output
ffmpeg_command = [
    "ffmpeg", 
    "-f", "v4l2", 
    "-video_size", "1280x720", 
    "-thread_queue_size", "1024", 
    "-i", "/dev/video0",
    "-f", "alsa", 
    "-thread_queue_size", "1024", 
    "-channels", "1",         # Force mono audio input
    "-sample_rate", "44100",  # Use supported sample rate
    "-itsoffset", "1.0", 
    "-i", "hw:2,0", 
    "-preset", "veryfast",
    "-ac", "1",              # Force mono audio output
    "-ar", "44100",          # Set audio rate in output
    "-r", "30", 
    "-vf", "transpose=1,transpose=1", 
    "-f", "segment", 
    "-segment_time", "10", 
    "-segment_format", "mkv",
    os.path.join(SEGMENT_DIR, "output%03d.mkv")
]

def print_timestamp(message):
    """Print a message with timestamp for better logging"""
    current_time = datetime.now().strftime("%H:%M:%S")
    print(f"[{current_time}] {message}")

def monitor_segments():
    """Monitor segment directory and print when new segments are created"""
    global segment_count, start_time
    last_count = 0
    
    while True:
        # Get current count of segment files
        try:
            files = os.listdir(SEGMENT_DIR)
            current_count = len([f for f in files if f.startswith("output") and f.endswith(".mkv")])
            
            # If we have a new segment
            if current_count > last_count:
                elapsed = (datetime.now() - start_time).total_seconds() if start_time else 0
                print_timestamp(f"New segment created! Total segments: {current_count} (Recording time: {elapsed:.1f}s)")
                last_count = current_count
                segment_count = current_count
            
            # Check recording time and print progress
            if start_time:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > 0 and elapsed % 10 < 1:  # Print approximately every 10 seconds
                    print_timestamp(f"Recording in progress... ({elapsed:.1f}s elapsed, {current_count} segments)")
                    
                # Every 60 seconds, give a reminder about the 'r' key
                if elapsed > 0 and elapsed % 60 < 1:
                    print_timestamp("Press 'r' key or the button to save the last 60 seconds of video")
        except Exception as e:
            print_timestamp(f"Error monitoring segments: {e}")
            
        time.sleep(1)

def start_recording():
    """Start the FFmpeg recording process with error handling"""
    global ffmpeg_process, start_time
    try:
        print_timestamp("Starting recording...")
        
        # Start FFmpeg with pipe to capture output
        ffmpeg_process = subprocess.Popen(
            ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        
        # Set recording start time
        start_time = datetime.now()
        
        # Check if process started successfully
        time.sleep(1)
        if ffmpeg_process.poll() is not None:
            # Process terminated immediately
            stderr = ffmpeg_process.stderr.read()
            print_timestamp(f"FFmpeg failed to start with error:")
            print(stderr)
            return False
            
        print_timestamp("Recording started successfully!")
        return True
    except Exception as e:
        print_timestamp(f"Error starting recording: {e}")
        return False

def button_pressed(*args):
    """Handle button press to save recording"""
    global ffmpeg_process, segment_count
    print_timestamp("\n------------------------------------------------------")
    print_timestamp("⏺️ BUTTON PRESSED - SAVING VIDEO ⏺️")
    print_timestamp("------------------------------------------------------")
    
    # Show current file count
    try:
        files = sorted(os.listdir(SEGMENT_DIR), key=lambda x: os.path.getctime(os.path.join(SEGMENT_DIR, x)))
        print_timestamp(f"Found {len(files)} segment files")
        for i, f in enumerate(files):
            creation_time = datetime.fromtimestamp(os.path.getctime(os.path.join(SEGMENT_DIR, f)))
            time_str = creation_time.strftime("%H:%M:%S")
            print(f"  {i+1}. {f} (created at {time_str})")
    except Exception as e:
        print_timestamp(f"Error listing files: {e}")
    
    # Stop the FFmpeg process
    if ffmpeg_process and ffmpeg_process.poll() is None:
        print_timestamp("Stopping recording process...")
        ffmpeg_process.terminate()
        
        # Wait for process to terminate
        timeout = 10  # seconds
        start_wait = time.time()
        while ffmpeg_process.poll() is None and time.time() - start_wait < timeout:
            print_timestamp("Waiting for FFmpeg to terminate...")
            time.sleep(1)
            
        # If it's still running, force kill it
        if ffmpeg_process.poll() is None:
            print_timestamp("FFmpeg did not terminate gracefully, forcing kill...")
            ffmpeg_process.kill()
        
        ffmpeg_process.wait()
        print_timestamp("Recording stopped.")
    else:
        print_timestamp("No active recording process found.")

    # Get the current time and format it as a string
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    # Get a list of the segment files, sorted by creation time
    try:
        files = sorted(os.listdir(SEGMENT_DIR), key=lambda x: os.path.getctime(os.path.join(SEGMENT_DIR, x)))
    except Exception as e:
        print_timestamp(f"Error listing segment files: {e}")
        start_recording()
        return

    # Check if we have enough files
    if len(files) < 6:
        print_timestamp(f"⚠️ Not enough segment files (found {len(files)}, need at least 6)")
        print_timestamp(f"Cannot create video - waiting for more segments to be created")
        start_recording()
        return

    # Create a list of the six oldest segment files
    segments = files[0:6]  # Use the oldest 6 files
    print_timestamp(f"Using {len(segments)} segments for video creation")

    # Check if all the necessary files exist and are accessible
    all_files_ok = True
    for segment in segments:
        path = os.path.join(SEGMENT_DIR, segment)
        if not os.path.exists(path):
            print_timestamp(f"⚠️ File {path} does not exist.")
            all_files_ok = False
            break
        if not os.access(path, os.R_OK):
            print_timestamp(f"⚠️ File {path} is not accessible.")
            all_files_ok = False
            break
            
    if not all_files_ok:
        print_timestamp("Cannot create video due to missing or inaccessible files")
        start_recording()
        return

    # Create a temporary file that contains the list of files to concatenate
    temp_file = os.path.join(SEGMENT_DIR, "temp.txt")
    try:
        with open(temp_file, "w") as f:
            for segment in segments:
                path = os.path.join(SEGMENT_DIR, segment)
                f.write(f"file '{path}'\n")
                print_timestamp(f"Added {segment} to concat list")

        # Create output filename with path
        output_file = os.path.join(os.path.dirname(SEGMENT_DIR), f"{timestamp}.mkv")
        print_timestamp(f"Creating video: {output_file}")
        
        # Create an FFmpeg command to concatenate the segment files
        ffmpeg_concat_command = [
            "ffmpeg", 
            "-f", "concat", 
            "-safe", "0", 
            "-i", temp_file, 
            "-c", "copy",  # Copy codecs without re-encoding for speed
            output_file
        ]
        
        # Run the FFmpeg command
        print_timestamp("Starting concat process...")
        concat_process = subprocess.Popen(
            ffmpeg_concat_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Wait for concatenation to complete
        stdout, stderr = concat_process.communicate()
        
        if concat_process.returncode != 0:
            print_timestamp(f"⚠️ Error concatenating files:")
            print(stderr)
        else:
            # Check if output file was created and get size
            if os.path.exists(output_file):
                size_mb = os.path.getsize(output_file) / (1024 * 1024)
                print_timestamp(f"✅ SUCCESS! Created {output_file} ({size_mb:.2f} MB)")
            else:
                print_timestamp(f"⚠️ Output file not found: {output_file}")

        # Delete the temporary file
        if os.path.exists(temp_file):
            os.remove(temp_file)
            print_timestamp("Temporary concat file deleted")
            
    except Exception as e:
        print_timestamp(f"⚠️ Error during file concatenation: {e}")
    
    # Restart the FFmpeg process
    print_timestamp("Restarting recording...")
    start_recording()
    print_timestamp("------------------------------------------------------")

# Main program
def main():
    # Initial setup
    print_timestamp("🎥 ABR Glass Recording System v0.1 🎥")
    print_timestamp("======================================")
    print_timestamp(f"Segment files will be stored in: {SEGMENT_DIR}")
    
    # Set up the button press interrupt
    GPIO.add_event_detect(BUTTON_GPIO, GPIO.FALLING, callback=button_pressed, bouncetime=300)
    print_timestamp(f"Button configured on GPIO {BUTTON_GPIO}")

    # Set up the keyboard press event
    keyboard.on_press_key("r", button_pressed)
    print_timestamp("Keyboard 'r' key configured for manual triggering")
    print_timestamp("======================================")
    
    # Start monitor thread for segments
    monitor_thread = threading.Thread(target=monitor_segments, daemon=True)
    monitor_thread.start()
    
    # Start initial recording
    if not start_recording():
        print_timestamp("⚠️ Failed to start recording. Please check your camera and audio setup.")
        GPIO.cleanup()
        return

    # Main loop
    try:
        print_timestamp("System ready! Press the button or 'r' key to save video.")
        while True:
            # Get a list of the segment files
            try:
                files = sorted(os.listdir(SEGMENT_DIR), key=lambda x: os.path.getctime(os.path.join(SEGMENT_DIR, x)))

                # If there are more than 7 files, delete the oldest ones
                while len(files) > 7:
                    file_to_delete = os.path.join(SEGMENT_DIR, files.pop(0))
                    try:
                        os.remove(file_to_delete)
                        print_timestamp(f"Deleted old segment file: {os.path.basename(file_to_delete)}")
                    except Exception as e:
                        print_timestamp(f"Error deleting old file {file_to_delete}: {e}")
            except Exception as e:
                print_timestamp(f"Error managing segment files: {e}")

            # Check if ffmpeg is still running, restart if needed
            if ffmpeg_process.poll() is not None:
                print_timestamp("⚠️ FFmpeg process stopped unexpectedly, restarting...")
                start_recording()

            time.sleep(1)
    except KeyboardInterrupt:
        print_timestamp("\nExiting program...")
        if ffmpeg_process and ffmpeg_process.poll() is None:
            ffmpeg_process.terminate()
            ffmpeg_process.wait()
        GPIO.cleanup()
        print_timestamp("GPIO cleaned up. Goodbye!")
    except Exception as e:
        print_timestamp(f"Unexpected error: {e}")
        if ffmpeg_process and ffmpeg_process.poll() is None:
            ffmpeg_process.terminate()
            ffmpeg_process.wait()
        GPIO.cleanup()

if __name__ == "__main__":
    main()