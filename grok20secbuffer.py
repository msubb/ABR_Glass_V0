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
os.makedirs(SEGMENT_DIR, exist_ok=True)
os.makedirs(SAVE_DIR, exist_ok=True)

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
    
    # FFmpeg command for continuous segment recording
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
    
    while recording_active:
        if save_in_progress:
            time.sleep(1)
            continue
        
        files = sorted(glob.glob(os.path.join(SEGMENT_DIR, "output*.mkv")), 
                      key=lambda x: os.path.getctime(x))
        
        # Buffer ready with at least 5 segments (~25 seconds)
        if len(files) >= 5 and not buffer_ready:
            buffer_ready = True
            print("✅ Buffer ready! Press button or 'r' key anytime to save a ~20 second clip.")
        
        # Keep up to 10 segments
        while len(files) > 10:
            oldest_file = files.pop(0)
            try:
                os.remove(oldest_file)
                segment_timings = [s for s in segment_timings if s['file'] != oldest_file]
            except Exception as e:
                print(f"Error removing old segment {oldest_file}: {e}")
        
        time.sleep(1)

# Function to save the buffer
def save_buffer():
    """Saves a clip with at least 20 seconds before the button press and the press moment."""
    global recording_active, buffer_ready, button_press_time, save_in_progress, segment_timings, expected_segment_duration
    
    if not buffer_ready:
        print("Buffer not ready yet. Wait for at least 25 seconds of recording.")
        return
    
    if save_in_progress:
        print("Save already in progress. Please wait...")
        return
    
    save_in_progress = True
    button_press_time = time.time()
    print(f"🔴 Button pressed at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    # Ensure current segment finishes
    print("Waiting to ensure capture of button press moment...")
    time.sleep(6)
    
    print("Finding segments that include 20 seconds before button press...")
    
    target_start_time = button_press_time - 25 # 5 seconds before button press test cause it was under 20
    selected_segments = []
    
    # Select overlapping segments
    for segment in segment_timings:
        if segment['end_time'] > target_start_time and segment['start_time'] <= button_press_time:
            selected_segments.append(segment['file'])
    
    # Ensure minimum duration
    total_duration = len(selected_segments) * expected_segment_duration
    if total_duration < 20 and selected_segments:
        earliest_segment = min(selected_segments, key=lambda x: int(os.path.basename(x).split('.')[0][6:]))
        segment_number = int(os.path.basename(earliest_segment).split('.')[0][6:]) - 1
        while total_duration < 20 and segment_number >= 0:
            prev_segment = os.path.join(SEGMENT_DIR, f"output{segment_number:03d}.mkv")
            if os.path.exists(prev_segment) and prev_segment not in selected_segments:
                selected_segments.insert(0, prev_segment)
                total_duration += expected_segment_duration
            segment_number -= 1
    
    # Fallback to recent segments
    if not selected_segments or total_duration < 20:
        print("Insufficient segments found, using most recent ones as fallback.")
        files = sorted(glob.glob(os.path.join(SEGMENT_DIR, "output*.mkv")),
                       key=lambda x: os.path.getctime(x))
        selected_segments = files[-5:]
        total_duration = len(selected_segments) * expected_segment_duration
    
    # Sort segments
    selected_segments = sorted(selected_segments, key=lambda x: int(os.path.basename(x).split('.')[0][6:]))
    
    print(f"Selected {len(selected_segments)} segments for approximately {total_duration:.2f} seconds of footage")
    
    # Copy segments
    temp_segments = []
    for i, segment in enumerate(selected_segments):
        temp_path = os.path.join(SAVE_DIR, f"temp_{i:03d}.mkv")
        shutil.copy2(segment, temp_path)
        temp_segments.append(temp_path)
    
    print("Copied segments to temp directory for processing")
    
    # Create concat file
    concat_file = os.path.join(SAVE_DIR, "concat.txt")
    with open(concat_file, "w") as f:
        for segment in temp_segments:
            f.write(f"file '{segment}'\n")
    
    # Generate output filename
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    output_file = f"{timestamp}.mkv"
    
    # Concatenate segments
    ffmpeg_concat_command = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_file,
        "-c", "copy",
        output_file
    ]
    
    print("Running FFmpeg to combine segments...")
    concat_process = subprocess.Popen(ffmpeg_concat_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = concat_process.communicate()
    
    if concat_process.returncode != 0:
        print(f"Error combining segments: {stderr.decode()}")
        save_in_progress = False
        return
    
    # Clean up
    os.remove(concat_file)
    for temp_file in temp_segments:
        os.remove(temp_file)
    
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
    except:
        print(f"✅ RECORDING SAVED: {output_file}")
    
    save_in_progress = False
    print("Continuing to record... Press button or 'r' key to save another clip.")

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
        GPIO.add_event_detect(BUTTON_GPIO, GPIO.FALLING, callback=lambda x: save_buffer_handler(), bouncetime=1000)
        keyboard.on_press_key("r", save_buffer_handler)
        
        start_continuous_recording()
        
        buffer_thread = threading.Thread(target=manage_buffer)
        buffer_thread.daemon = True
        buffer_thread.start()
        
        tracking_thread = threading.Thread(target=track_segments)
        tracking_thread.daemon = True
        tracking_thread.start()
        
        print("Continuous recording started. Buffering first 25 seconds...")
        print("After buffer is ready, press button or 'r' key anytime to save a clip.")
        
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