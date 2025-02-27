#!/usr/bin/env python3
import os
import subprocess
import time
from datetime import datetime

# Get current timestamp for the filename
now = datetime.now()
timestamp = now.strftime("%Y%m%d_%H%M%S")
output_file = f"audio_test_hw_2_0_{timestamp}.wav"

print(f"Testing audio recording from hw:2,0...")
print(f"Recording to file: {output_file}")
print("Press Ctrl+C to stop recording")

# More explicit FFmpeg command for mono audio
ffmpeg_command = [
    "ffmpeg",
    "-hide_banner",         # Less verbose output
    "-f", "alsa",           # Use ALSA input
    "-channels", "1",       # Force mono - alternative syntax
    "-sample_rate", "44100", # Explicit sample rate syntax
    "-i", "hw:2,0",         # Audio device
    "-acodec", "pcm_s16le", # Force 16-bit PCM codec
    "-ac", "1",             # Force mono again in output
    "-t", "10",             # Record for 10 seconds
    "-y",                   # Overwrite output file if exists
    output_file             # Output file
]

# Alternative command using arecord instead of ffmpeg
arecord_command = [
    "arecord",
    "-D", "hw:2,0",         # Device
    "-f", "S16_LE",         # Format
    "-c", "1",              # Channels
    "-r", "44100",          # Rate
    "-d", "10",             # Duration (seconds)
    output_file             # Output file
]

try:
    # Uncomment the command you want to try
    print("Trying with FFmpeg...")
    process = subprocess.Popen(ffmpeg_command)
    
    # Wait for process to complete or for user to interrupt
    process.wait()
    
    # Try arecord if ffmpeg fails
    if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
        print("\nFFmpeg failed. Trying with arecord...")
        process = subprocess.Popen(arecord_command)
        process.wait()
    
    if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
        print(f"\nRecording complete. File saved as {output_file}")
        print(f"File size: {os.path.getsize(output_file)} bytes")
    else:
        print("\nRecording failed. No valid output file was created.")
        
except KeyboardInterrupt:
    # Handle Ctrl+C
    print("\nRecording stopped by user")
    process.terminate()
    process.wait()
    
    if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
        print(f"File saved as {output_file}")
        print(f"File size: {os.path.getsize(output_file)} bytes")
    else:
        print("No valid output file was created")

# Optional: Play back the recording if it exists
if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
    print("\nWould you like to play back the recording? (y/n)")
    choice = input().lower()
    if choice == 'y':
        playback_command = ["aplay", output_file]
        subprocess.run(playback_command)