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

# Set up the button GPIO
BUTTON_GPIO = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Directory where the segment files are stored
SEGMENT_DIR = "/home/boazburnett/projects/abr-glass/ABR_Glass_V0/segments"
# Directory for temporary storage of segments during saving
SAVE_DIR = "/home/boazburnett/projects/abr-glass/ABR_Glass_V0/save_temp"

# Ensure directories exist
os.makedirs(SEGMENT_DIR, exist_ok=True)
os.makedirs(SAVE_DIR, exist_ok=True)

# Function to save the buffer
def save_buffer():
    global recording_active, buffer_ready, button_press_time, save_in_progress
    
    if not buffer_ready:
        print("Buffer not ready yet. Wait for at least 30 seconds of recording.")
        return
    
    if save_in_progress:
        print("Save already in progress. Please wait...")
        return
    
    save_in_progress = True
    button_press_time = time.time()
    print(f"🔴 Button pressed at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    # Get the current time for the output filename
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    output_file = f"{timestamp}.mkv"
    
    # Wait a little to ensure the current segment completes and a new one starts
    # This ensures we have a segment that contains the button press
    print("Waiting to ensure capture of button press moment...")
    time.sleep(12)
    
    print(f"Finding segments that include 20 seconds before button press...")
    
    # Get all segment files with their creation and modification times
    segment_info = []
    for file in glob.glob(os.path.join(SEGMENT_DIR, "output*.mkv")):
        create_time = os.path.getctime(file)
        mod_time = os.path.getmtime(file)
        segment_info.append((file, create_time, mod_time))
    
    # Sort by creation time
    segment_info.sort(key=lambda x: x[1])
    
    if len(segment_info) < 2:
        print(f"Not enough segment files found. Only found {len(segment_info)} files.")
        save_in_progress = False
        return
    
    # Find segments that were created or modified around the button press time
    selected_segments = []
    button_segment_found = False
    target_start_time = button_press_time - 20  # Target 20 seconds before button press
    
    # First, find the segment that was being written when button was pressed
    for i, (file, create_time, mod_time) in enumerate(segment_info):
        # If this segment was being modified when button was pressed
        if create_time <= button_press_time <= mod_time:
            button_segment_found = True
            selected_segments.append(file)
            print(f"Found segment active during button press: {os.path.basename(file)}")
            
            # Work backwards to get segments covering 20 seconds before button press
            current_time = create_time
            j = i - 1
            while j >= 0 and current_time > target_start_time:
                selected_segments.insert(0, segment_info[j][0])
                current_time = segment_info[j][1]  # creation time of previous segment
                print(f"Added earlier segment: {os.path.basename(segment_info[j][0])}")
                j -= 1
            break
    
    # If we didn't find a segment being written at button press,
    # take the most recent segments that cover the time period
    if not button_segment_found:
        print("Could not find segment active during button press, using most recent segments")
        # Start with the most recent segment
        selected_segments.append(segment_info[-1][0])
        current_time = segment_info[-1][1]
        
        # Work backwards through segments
        for i in range(len(segment_info) - 2, -1, -1):
            if current_time > target_start_time:
                selected_segments.insert(0, segment_info[i][0])
                current_time = segment_info[i][1]
            else:
                break
    
    print(f"Selected {len(selected_segments)} segments for approximately 20+ seconds of footage")
    
    # Copy selected segments to temporary directory to avoid issues with buffer management
    temp_segments = []
    for i, segment in enumerate(selected_segments):
        temp_path = os.path.join(SAVE_DIR, f"temp_{i:03d}.mkv")
        shutil.copy2(segment, temp_path)
        temp_segments.append(temp_path)
    
    print(f"Copied segments to temp directory for processing")
    
    # Create a temporary file that contains the list of files to concatenate
    concat_file = os.path.join(SAVE_DIR, "concat.txt")
    with open(concat_file, "w") as f:
        for segment in temp_segments:
            f.write(f"file '{segment}'\n")
    
    # Create an FFmpeg command to concatenate the segment files
    ffmpeg_concat_command = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_file,
        "-c", "copy",  # Use copy to avoid re-encoding
        output_file
    ]
    
    print("Running FFmpeg to combine segments...")
    # Run the FFmpeg command
    concat_process = subprocess.Popen(ffmpeg_concat_command, 
                                       stdout=subprocess.PIPE, 
                                       stderr=subprocess.PIPE)
    stdout, stderr = concat_process.communicate()
    
    # Check if concatenation was successful
    if concat_process.returncode != 0:
        print(f"Error combining segments: {stderr.decode()}")
        save_in_progress = False
        return
    
    # Clean up temporary files
    os.remove(concat_file)
    for temp_file in temp_segments:
        os.remove(temp_file)
    
    # Get the duration of the saved file
    duration_command = [
        "ffprobe", 
        "-v", "error", 
        "-show_entries", 
        "format=duration", 
        "-of", 
        "default=noprint_wrappers=1:nokey=1", 
        output_file
    ]
    
    try:
        duration = float(subprocess.check_output(duration_command).decode('utf-8').strip())
        print(f"✅ RECORDING SAVED: {output_file} (Duration: {duration:.2f} seconds)")
    except:
        print(f"✅ RECORDING SAVED: {output_file}")
    
    print("Continuing to record... Press button or 'r' key to save another clip.")
    save_in_progress = False

# Function to handle button press or 'r' key
def save_buffer_handler(*args):
    # Start save_buffer in a new thread so it doesn't block the main thread
    save_thread = threading.Thread(target=save_buffer)
    save_thread.daemon = True
    save_thread.start()

# Buffer management function
def manage_buffer():
    global buffer_ready
    
    # Keep more segments than we need to ensure we have enough history
    buffer_segments = 8  # ~80 seconds of buffer (more than needed to ensure we have enough)
    
    while recording_active:
        if save_in_progress:
            # Don't delete segments while saving
            time.sleep(1)
            continue
            
        # Get a list of the segment files, sorted by creation time
        files = sorted(glob.glob(os.path.join(SEGMENT_DIR, "output*.mkv")), 
                      key=lambda x: os.path.getctime(x))
        
        # If we have at least 3 complete segments, mark buffer as ready
        if len(files) >= 3 and not buffer_ready:
            buffer_ready = True
            print("✅ Buffer ready! Press button or 'r' key anytime to save a ~20 second clip.")
        
        # If there are more files than needed for our buffer, delete the oldest ones
        while len(files) > buffer_segments:
            oldest_file = files.pop(0)
            try:
                os.remove(oldest_file)
            except Exception as e:
                print(f"Error removing old segment {oldest_file}: {e}")
        
        time.sleep(1)

# Start the continuous recording
def start_continuous_recording():
    global ffmpeg_process, recording_active
    
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
    
    # Start the FFmpeg command for continuous segment recording with shorter segments
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
        "-segment_time", "5",  # Shorter segments for more precise timing
        "-segment_format", "mkv",
        "-reset_timestamps", "1",  # Reset timestamps for each segment
        os.path.join(SEGMENT_DIR, "output%03d.mkv")
    ]
    
    print("Starting continuous recording...")
    ffmpeg_process = subprocess.Popen(ffmpeg_command, 
                                      stdout=subprocess.DEVNULL, 
                                      stderr=subprocess.STDOUT)

# Main function
def main():
    global ffmpeg_process, recording_active
    
    try:
        # Set up the button press interrupt
        GPIO.add_event_detect(BUTTON_GPIO, GPIO.FALLING, callback=lambda x: save_buffer_handler(), bouncetime=1000)
        
        # Set up the keyboard press event
        keyboard.on_press_key("r", save_buffer_handler)
        
        # Start continuous recording
        start_continuous_recording()
        
        # Start buffer management in a separate thread
        buffer_thread = threading.Thread(target=manage_buffer)
        buffer_thread.daemon = True
        buffer_thread.start()
        
        print("Continuous recording started. Buffering first 30 seconds...")
        print("After buffer is ready, press button or 'r' key anytime to save a clip.")
        
        # Keep the main thread running
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