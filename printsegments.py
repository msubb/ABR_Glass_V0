import os

# Directory where the segment files are stored
SEGMENT_DIR = "/home/boazburnett/projects/abr-glass/ABR_Glass_V0/segments"

# Get a list of the files in the directory, sorted by creation time
files = sorted(os.listdir(SEGMENT_DIR), key=lambda x: os.path.getctime(os.path.join(SEGMENT_DIR, x)))

# Print the sorted list of files
for file in files[0:6]:
    print(file)