import cv2
import time
import numpy as np

# Define the duration of the buffer
buffer_duration = 10  # seconds

# Create buffer for the video
video_buffer = []


def record_to_buffer(duration):
    global video_buffer  # Declare video_buffer as a global variable
    cap = cv2.VideoCapture(0)

    while True:
        ret, frame = cap.read()
        if ret:
            timestamp = time.time()
            video_buffer.append((frame, timestamp))

            # Display the resulting frame
            cv2.imshow('frame', frame)

            # If 'r' is pressed, write the buffer to a file
            if cv2.waitKey(1) & 0xFF == ord('r'):
                height, width, _ = video_buffer[0][0].shape
                timestamps = [timestamp for frame, timestamp in video_buffer]
                frame_rate = len(timestamps) / (max(timestamps) - min(timestamps))
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')

                # Include the timestamp in the file name
                filename = 'temp_video_' + str(int(time.time())) + '.mp4'
                out = cv2.VideoWriter(filename, fourcc, frame_rate, (width, height))

                # Only write the most recent 10 seconds of frames to the file
                cutoff_time = time.time() - buffer_duration
                for frame, timestamp in video_buffer:
                    if timestamp >= cutoff_time:
                        out.write(frame)
                video_buffer = []

            # If the buffer is older than the specified duration, remove the oldest frames
            cutoff_time = time.time() - buffer_duration
            video_buffer = [(frame, timestamp) for frame, timestamp in video_buffer if timestamp >= cutoff_time]

            # If 'q' is pressed, break from the loop
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        else:
            break

    # Release everything when done
    cap.release()
    cv2.destroyAllWindows()


# Record to the buffer
record_to_buffer(buffer_duration)