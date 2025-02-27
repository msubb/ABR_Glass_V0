import os
import time
import subprocess
import keyboard
from datetime import datetime, timedelta
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
recording_start_time = None  # Track recording session start time

# Set up the button GPIO
BUTTON_GPIO = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Directory configuration
SEGMENT_DIR = "/home/boazburnett/projects/abr-glass/ABR_Glass_V0/segments"
SAVE_DIR = "/home/boazburnett/projects/abr-glass/ABR_Glass_V0/save_temp"
os.makedirs(SEGMENT_DIR, exist_ok=True)
os.makedirs(SAVE_DIR, exist_ok=True)

# Constants
SEGMENT_DURATION = 5  # Seconds per segment
BUFFER_SEGMENTS = 12  # Keep 60 seconds of buffer (12 * 5s)
PRE_BUFFER_DURATION = 20  # Seconds to capture before button press
POST_BUFFER_DURATION = 5  # Seconds to capture after button press

def save_buffer():
    global recording_active, buffer_ready, button_press_time, save_in_progress, recording_start_time

    if not buffer_ready:
        print("Buffer not ready yet. Wait for at least 30 seconds of recording.")
        return

    if save_in_progress:
        print("Save already in progress. Please wait...")
        return

    save_in_progress = True
    button_press_time = time.time()
    print(f"🔴 Button pressed at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")

    # Calculate target time window
    target_start = button_press_time - PRE_BUFFER_DURATION
    target_end = button_press_time + POST_BUFFER_DURATION

    # Get all segments sorted by creation time
    segments = sorted(glob.glob(os.path.join(SEGMENT_DIR, "output*.mkv")),
                      key=os.path.getctime)

    if not segments:
        print("No segments available for saving.")
        save_in_progress = False
        return

    # Find all segments that overlap with the target time window
    selected_segments = []
    for seg in segments:
        seg_ctime = os.path.getctime(seg)
        seg_mtime = os.path.getmtime(seg)
        
        # Calculate segment time window (creation to modification time)
        seg_start = seg_ctime
        seg_end = seg_mtime
        
        # Check if segment overlaps with target window
        if (seg_start <= target_end) and (seg_end >= target_start):
            selected_segments.append(seg)

    if not selected_segments:
        print("No overlapping segments found, using most recent")
        # Fallback: use last 4 segments (20 seconds)
        selected_segments = segments[-4:]

    print(f"Selected {len(selected_segments)} segments covering {len(selected_segments)*SEGMENT_DURATION}s")

    # Copy segments to temp directory
    temp_segments = []
    for i, seg in enumerate(selected_segments):
        temp_path = os.path.join(SAVE_DIR, f"temp_{i:03d}.mkv")
        shutil.copy2(seg, temp_path)
        temp_segments.append(temp_path)

    # Generate output filename
    timestamp = datetime.fromtimestamp(button_press_time).strftime("%Y%m%d_%H%M%S")
    output_file = f"{timestamp}.mkv"

    # Create concat list
    concat_file = os.path.join(SAVE_DIR, "concat.txt")
    with open(concat_file, "w") as f:
        for seg in temp_segments:
            f.write(f"file '{seg}'\n")

    # Combine segments with FFmpeg
    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_file, "-c", "copy", output_file
        ], check=True)
        
        # Verify duration
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", output_file
        ], capture_output=True, text=True)
        
        duration = float(result.stdout.strip())
        print(f"✅ RECORDING SAVED: {output_file} (Duration: {duration:.2f}s)")
        
    except subprocess.CalledProcessError as e:
        print(f"Error combining segments: {e.stderr}")
    finally:
        # Cleanup
        os.remove(concat_file)
        for f in temp_segments:
            os.remove(f)

    print("Continuing to record... Press button or 'r' key to save another clip.")
    save_in_progress = False

def manage_buffer():
    global buffer_ready

    while recording_active:
        if save_in_progress:
            time.sleep(1)
            continue
            
        segments = sorted(glob.glob(os.path.join(SEGMENT_DIR, "output*.mkv")),
                         key=os.path.getctime)
        
        # Mark buffer ready when we have at least 6 segments (30s)
        buffer_ready = len(segments) >= 6
        if buffer_ready and not buffer_ready:
            print("✅ Buffer ready! Press button or 'r' key to save clips.")
        
        # Remove old segments while maintaining buffer
        while len(segments) > BUFFER_SEGMENTS:
            oldest = segments.pop(0)
            try:
                os.remove(oldest)
                print(f"Removed old segment: {os.path.basename(oldest)}")
            except Exception as e:
                print(f"Error removing {oldest}: {e}")
        
        time.sleep(1)

def start_continuous_recording():
    global ffmpeg_process, recording_start_time

    # Clear old segments
    for f in glob.glob(os.path.join(SEGMENT_DIR, "output*.mkv")):
        os.remove(f)
        
    # Start FFmpeg with timestamped segments
    recording_start_time = time.time()
    ffmpeg_command = [
        "ffmpeg", "-f", "v4l2", "-video_size", "1280x720",
        "-thread_queue_size", "1024", "-i", "/dev/video0",
        "-f", "alsa", "-thread_queue_size", "1024",
        "-channels", "1", "-sample_rate", "44100",
        "-itsoffset", "1.0", "-i", "hw:5,0",
        "-preset", "veryfast", "-ac", "1", "-ar", "44100",
        "-r", "30", "-vf", "transpose=1,transpose=1",
        "-f", "segment", "-segment_time", str(SEGMENT_DURATION),
        "-segment_format", "mkv", "-reset_timestamps", "1",
        os.path.join(SEGMENT_DIR, "output_%03d.mkv")
    ]
    
    ffmpeg_process = subprocess.Popen(ffmpeg_command,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.STDOUT)

def main():
    try:
        GPIO.add_event_detect(BUTTON_GPIO, GPIO.FALLING, 
                             callback=lambda x: save_buffer(), 
                             bouncetime=1000)
        keyboard.on_press_key("r", lambda _: save_buffer())
        
        start_continuous_recording()
        print("Continuous recording started. Buffering...")
        
        buffer_thread = threading.Thread(target=manage_buffer)
        buffer_thread.daemon = True
        buffer_thread.start()
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        recording_active = False
        if ffmpeg_process:
            ffmpeg_process.terminate()
        GPIO.cleanup()
        print("\nRecording stopped.")

if __name__ == "__main__":
    main()