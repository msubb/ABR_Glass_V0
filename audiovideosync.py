import os
import subprocess
import glob
import shutil

# Configuration
TEST_DIR = "/home/boazburnett/projects/abr-glass/ABR_Glass_V0/test_segments"
OUTPUT_DIR = "/home/boazburnett/projects/abr-glass/ABR_Glass_V0/sync_tests"
CONCAT_DIR = "/home/boazburnett/projects/abr-glass/ABR_Glass_V0/sync_concat_temp"

# List of delay values to test (positive means audio is delayed, negative means audio is earlier)
# Since -0.6 made audio too late, let's try a range of positive values and some smaller negative values
DELAY_VALUES = [0.4, 0.3, 0.2, 0.0, -0.1]

def generate_sync_tests():
    """
    Combines test segments and generates versions with different audio delays
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(CONCAT_DIR, exist_ok=True)
    
    # Get all test segments
    test_segments = sorted(glob.glob(os.path.join(TEST_DIR, "test_*.mkv")))
    
    if not test_segments:
        print("No test segments found. Save a clip with the main program first.")
        return
    
    print(f"Found {len(test_segments)} test segments")
    
    # First, combine the segments without any offset adjustment
    concat_file = os.path.join(CONCAT_DIR, "concat.txt")
    with open(concat_file, "w") as f:
        for segment in test_segments:
            f.write(f"file '{segment}'\n")
    
    original_combined = os.path.join(CONCAT_DIR, "original_combined.mkv")
    
    ffmpeg_concat_command = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_file,
        "-c", "copy",
        original_combined
    ]
    
    print("Combining segments without sync adjustment...")
    subprocess.run(ffmpeg_concat_command)
    
    # Now generate versions with different delay values
    for delay in DELAY_VALUES:
        delay_str = f"{abs(delay):.1f}"
        if delay < 0:
            delay_str = f"n{delay_str}"
        else:
            delay_str = f"p{delay_str}"
        
        output_file = os.path.join(OUTPUT_DIR, f"sync_test_{delay_str}.mp4")
        
        if delay < 0:
            # For negative delay (audio earlier), delay video
            cmd = [
                "ffmpeg", "-y",
                "-i", original_combined,
                "-itsoffset", str(abs(delay)),
                "-i", original_combined,
                "-map", "1:v", "-map", "0:a",
                "-c:v", "copy", "-c:a", "copy",
                output_file
            ]
        else:
            # For positive delay (audio later), delay audio
            cmd = [
                "ffmpeg", "-y",
                "-i", original_combined,
                "-itsoffset", str(delay),
                "-i", original_combined,
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "copy",
                output_file
            ]
        
        print(f"Generating test with {delay:.1f}s delay: {output_file}")
        subprocess.run(cmd)
    
    # Clean up
    os.remove(concat_file)
    
    print(f"Generated test videos in {OUTPUT_DIR}")
    print("Play these videos to determine which audio delay works best")

if __name__ == "__main__":
    generate_sync_tests()
