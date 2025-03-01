import os
import time
import subprocess
import keyboard
from datetime import datetime
import RPi.GPIO as GPIO
import threading
import glob
import shutil

# Global variables
ffmpeg_process = None
recording_active = True
buffer_ready = False
button_press_time = None
save_in_progress = False
segment_timings = []  # To track segment start/end times
recording_start_time = None
expected_segment_duration = 5.0  # Initial expected segment duration in seconds

# Set up the button GPIO
BUTTON_GPIO = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Directories
SEGMENT_DIR = "/home/boazburnett/projects/abr-glass/ABR_Glass_V0/segments"
SAVE_DIR = "/home/boazburnett/projects/abr-glass/ABR_Glass_V0/save_temp"
TEST_DIR = "/home/boazburnett/projects/abr-glass/ABR_Glass_V0/test_segments"
os.makedirs(SEGMENT_DIR, exist_ok=True)
os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(TEST_DIR, exist_ok=True)

def start_web_server():
    """Starts the web server in a separate process."""
    print("Starting web server for file access...")
    subprocess.Popen(["sudo", "python3", "network_server.py"], 
                    stdout=subprocess.DEVNULL, 
                    stderr=subprocess.DEVNULL)


# Function to start continuous recording
def start_continuous_recording():
    """Starts FFmpeg to record video in 5-second segments and sets the recording start time."""
    global ffmpeg_process, recording_active, recording_start_time
    
    # Clear any existing segments
    for file in glob.glob(os.path.join(SEGMENT_DIR, "output*.mkv")):
        try:
            os.remove(file)
        except Exception as e:
            print(f"Error removing old file {file}: {e}")
    
    for file in glob.glob(os.path.join(SAVE_DIR, "*.mkv")):
        try:
            os.remove(file)
        except Exception as e:
            print(f"Error removing old temp file {file}: {e}")
    
    # Record with no delay - we'll apply the sync during concatenation
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
        "-i", "hw:5,0",
        "-preset", "veryfast",
        "-ac", "1",
        "-ar", "44100",
        "-r", "30",
        "-vf", "transpose=1,transpose=1",
        "-f", "segment",
        "-segment_time", "5",
        "-segment_format", "mkv",
        "-reset_timestamps", "1",
        os.path.join(SEGMENT_DIR, "output%03d.mkv")
    ]
    
    print("Starting continuous recording...")
    ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    
    # Wait for the first segment and set recording_start_time
    while not glob.glob(os.path.join(SEGMENT_DIR, "output000.mkv")):
        time.sleep(0.1)
    recording_start_time = os.path.getctime(os.path.join(SEGMENT_DIR, "output000.mkv"))


# Function to track segment timings
def track_segments():
    """Tracks segment start and end times, adjusting duration to correct for drift."""
    global segment_timings, recording_start_time, expected_segment_duration
    last_adjusted = 0
    while recording_active:
        files = sorted(glob.glob(os.path.join(SEGMENT_DIR, "output*.mkv")),
                       key=lambda x: int(os.path.basename(x).split('.')[0][6:]))
        for file in files:
            if not any(s['file'] == file for s in segment_timings):
                segment_number = int(os.path.basename(file).split('.')[0][6:])
                start_time = recording_start_time + (segment_number * expected_segment_duration)
                end_time = start_time + expected_segment_duration
                segment_timings.append({'file': file, 'start_time': start_time, 'end_time': end_time})
        
        # Adjust expected_segment_duration every 10 segments
        if len(segment_timings) >= 10 and len(segment_timings) % 10 == 0 and len(segment_timings) != last_adjusted:
            last_adjusted = len(segment_timings)
            actual_total_time = time.time() - recording_start_time
            expected_segment_duration = actual_total_time / len(segment_timings)
            print(f"Adjusted expected_segment_duration to {expected_segment_duration:.2f} seconds")
        
        time.sleep(0.1)

# Buffer management function
def manage_buffer():
    """Manages the segment buffer, ensuring sufficient footage and removing old segments."""
    global buffer_ready, save_in_progress, segment_timings
    
    # Increase buffer size to 12 segments (~60 seconds) to ensure we always have enough footage
    MAX_SEGMENTS = 12
    
    while recording_active:
        if save_in_progress:
            time.sleep(1)
            continue
        
        files = sorted(glob.glob(os.path.join(SEGMENT_DIR, "output*.mkv")), 
                      key=lambda x: os.path.getctime(x))
        
        # Buffer ready with at least 6 segments (~30 seconds)
        if len(files) >= 6 and not buffer_ready:
            buffer_ready = True
            print("✅ Buffer ready! Press button or 'r' key anytime to save a clip of at least 25 seconds.")
        
        # Keep up to MAX_SEGMENTS segments
        while len(files) > MAX_SEGMENTS:
            oldest_file = files.pop(0)
            try:
                os.remove(oldest_file)
                segment_timings = [s for s in segment_timings if s['file'] != oldest_file]
            except Exception as e:
                print(f"Error removing old segment {oldest_file}: {e}")
        
        time.sleep(1)

# Function to save test segments for A/V sync testing
def save_segments_for_testing(segments):
    """Saves copies of selected segments for A/V sync testing."""
    # Clear previous test segments
    for file in glob.glob(os.path.join(TEST_DIR, "*.mkv")):
        try:
            os.remove(file)
        except Exception as e:
            print(f"Error removing test file {file}: {e}")
    
    # Copy selected segments
    for i, segment in enumerate(segments):
        test_path = os.path.join(TEST_DIR, f"test_{i:03d}.mkv")
        try:
            shutil.copy2(segment, test_path)
            print(f"Copied segment {os.path.basename(segment)} to {test_path}")
        except Exception as e:
            print(f"Error copying segment for testing: {e}")
    
    print(f"Copied {len(segments)} segments to {TEST_DIR} for A/V sync testing")
    print("You can now run test_av_sync.py to test different A/V sync delays")

# Function to save the buffer
def save_buffer():
    """Saves a clip with at least 25 seconds before the button press and the press moment."""
    global recording_active, buffer_ready, button_press_time, save_in_progress, segment_timings, expected_segment_duration

    if not buffer_ready:
        print("Buffer not ready yet. Wait for at least 30 seconds of recording.")
        return

    if save_in_progress:
        print("Save already in progress. Please wait...")
        return

    save_in_progress = True
    update_conversion_status(True)  # Set conversion status to True
    button_press_time = time.time()
    print(f"🔴 Button pressed at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")

    try:
        # Wait a bit longer to ensure the current segment completes
        print("Waiting to ensure capture of button press moment...")
        time.sleep(7)

        # Get all current segments
        all_segments = sorted(
            glob.glob(os.path.join(SEGMENT_DIR, "output*.mkv")),
            key=lambda x: int(os.path.basename(x).split('.')[0][6:])
        )

        # Find the segment that contains the button press
        button_segment = None
        active_segment_number = None

        for segment in segment_timings:
            if segment['start_time'] <= button_press_time <= segment['end_time']:
                button_segment = segment['file']
                active_segment_number = int(os.path.basename(button_segment).split('.')[0][6:])
                break

        if button_segment is None:
            # If we couldn't find the button segment, use the most recent one
            button_segment = all_segments[-1]
            active_segment_number = int(os.path.basename(button_segment).split('.')[0][6:])
            print(f"Button press segment not identified, using most recent segment {button_segment}")
        else:
            print(f"Button press detected in segment {button_segment}")

        # Get at least 5 segments before the button segment (25 seconds)
        target_segments = []
        earliest_segment_number = max(0, active_segment_number - 5)

        for i in range(earliest_segment_number, active_segment_number + 1):
            segment_path = os.path.join(SEGMENT_DIR, f"output{i:03d}.mkv")
            if os.path.exists(segment_path):
                target_segments.append(segment_path)

        # If we don't have enough segments, grab as many as we can from the existing ones
        if len(target_segments) < 6:
            print(f"Only found {len(target_segments)} segments, need at least 6 for 25+ seconds")
            available_segments = sorted(
                all_segments,
                key=lambda x: int(os.path.basename(x).split('.')[0][6:])
            )
            # Use all available segments if we don't have enough
            if len(available_segments) <= 6:
                target_segments = available_segments
            else:
                # Include the button segment and the 5 segments before it
                button_index = available_segments.index(button_segment) if button_segment in available_segments else len(available_segments) - 1
                start_index = max(0, button_index - 5)
                target_segments = available_segments[start_index:button_index+1]

        # Ensure segments are sorted
        target_segments = sorted(
            target_segments,
            key=lambda x: int(os.path.basename(x).split('.')[0][6:])
        )

        total_duration = len(target_segments) * expected_segment_duration
        print(f"Selected {len(target_segments)} segments for approximately {total_duration:.2f} seconds of footage")
        print(f"Segments: {[os.path.basename(s) for s in target_segments]}")

        # Save segments for A/V sync testing
        save_segments_for_testing(target_segments)

        # First combine segments without A/V sync adjustment
        temp_combined = os.path.join(SAVE_DIR, "temp_combined.mkv")

        # Create concat file
        concat_file = os.path.join(SAVE_DIR, "concat.txt")
        with open(concat_file, "w") as f:
            for segment in target_segments:
                f.write(f"file '{segment}'\n")

        # Concatenate segments without sync adjustment
        ffmpeg_concat_command = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            temp_combined
        ]
        print("Running FFmpeg to combine segments...")
        concat_process = subprocess.Popen(ffmpeg_concat_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = concat_process.communicate()

        if concat_process.returncode != 0:
            print(f"Error combining segments: {stderr.decode()}")
            return

        # Generate output filename (now using MP4 extension)
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        output_file = f"{timestamp}.mp4"

        # Now apply A/V sync adjustment and convert to MP4 (iPhone compatible)
        print("Applying 0.3s audio delay and converting to MP4 for mobile compatibility...")

        # Start timer for conversion
        conversion_start = time.time()

        sync_command = [
            "ffmpeg",
            "-i", temp_combined,
            "-itsoffset", "0.3",  # 0.3s audio delay
            "-i", temp_combined,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "libx264",    # Use H.264 video codec
            "-preset", "ultrafast",   # This speeds up encoding but increases file size, and reduces quality
            "-c:a", "aac",        # Use AAC audio codec
            "-b:a", "128k",       # Audio bitrate
            "-movflags", "+faststart",  # Optimize for web streaming
            output_file
        ]
        sync_process = subprocess.Popen(
            sync_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = sync_process.communicate()
        conversion_time = time.time() - conversion_start  # Conversion duration in seconds

        if sync_process.returncode != 0:
            print(f"Error applying A/V sync and converting to MP4: {stderr.decode()}")
            return

        # Get the final file size in MB
        file_size_bytes = os.path.getsize(output_file)
        file_size_mb = file_size_bytes / (1024 * 1024)

        print(f"Conversion Time: {conversion_time:.2f} seconds")
        print(f"Final File Size: {file_size_mb:.2f} MB")

        # Clean up
        os.remove(concat_file)
        os.remove(temp_combined)

        # Get actual duration
        duration_command = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            output_file
        ]
        try:
            duration = float(subprocess.check_output(duration_command).decode().strip())
            print(f"✅ RECORDING SAVED: {output_file} (Duration: {duration:.2f} seconds)")
        except Exception:
            print(f"✅ RECORDING SAVED: {output_file}")

    except Exception as e:
        print(f"Error saving recording: {e}")
    finally:
        # Always update status and reset save_in_progress flag
        update_conversion_status(False)  # Set conversion status to False
        save_in_progress = False
        print("Continuing to record... Press button or 'r' key to save another clip.")

def update_conversion_status(status):
    """Updates the conversion status for the web server."""
    try:
        status_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conversion_status.txt")
        with open(status_file, "w") as f:
            f.write("1" if status else "0")
    except Exception as e:
        print(f"Error updating conversion status: {e}")


# Handler for button or key press
def save_buffer_handler(*args):
    """Triggers save_buffer in a separate thread."""
    save_thread = threading.Thread(target=save_buffer)
    save_thread.daemon = True
    save_thread.start()

# Main function
def main():
    """Sets up and runs the recording system."""
    global ffmpeg_process, recording_active
    
    try:
        # Start web server
        start_web_server()
        
        GPIO.add_event_detect(BUTTON_GPIO, GPIO.FALLING, callback=lambda x: save_buffer_handler(), bouncetime=1000)
        keyboard.on_press_key("r", save_buffer_handler)
        
        start_continuous_recording()
        
        buffer_thread = threading.Thread(target=manage_buffer)
        buffer_thread.daemon = True
        buffer_thread.start()
        
        tracking_thread = threading.Thread(target=track_segments)
        tracking_thread.daemon = True
        tracking_thread.start()
        
        print("Continuous recording started. Buffering first 30 seconds...")
        print("After buffer is ready, press button or 'r' key anytime to save a clip.")
        print("Access recordings via web browser at http://raspberrypi.local or http://192.168.4.1")
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        recording_active = False
        if ffmpeg_process:
            ffmpeg_process.terminate()
            ffmpeg_process.wait()
        GPIO.cleanup()
        print("\nRecording stopped by user.")
    except Exception as e:
        recording_active = False
        if ffmpeg_process:
            ffmpeg_process.terminate()
            ffmpeg_process.wait()
        GPIO.cleanup()
        print(f"\nError: {e}")


if __name__ == "__main__":
    main()
