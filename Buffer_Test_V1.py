import os
import cv2
import time
import numpy as np
import pyaudio
import wave
import threading
from moviepy.editor import VideoFileClip, AudioFileClip

os.environ['IMAGEIO_FFMPEG_EXE'] = '/opt/homebrew/bin/ffmpeg'

# Define the duration of the buffer
buffer_duration = 10  # seconds

# defining the frame rate
frame_rate = 30.0

# Create buffer for the video
video_buffer = []

# Set the audio recording parameters
sample_rate = 48000  # Sample rate in Hz
channels = 1  # Number of audio channels (2 for stereo)

# Create buffer for the audio
audio_buffer = []

def record_to_buffer(duration):
    global video_buffer, audio_buffer  # Declare video_buffer and audio_buffer as global variables
    cap = cv2.VideoCapture(2)

    # Create a PyAudio instance
    p = pyaudio.PyAudio()

    # Start the audio recording
    stream = p.open(format=pyaudio.paInt16, channels=channels, rate=sample_rate, input=True, frames_per_buffer=4096)

    # Create a lock for thread-safe access to the audio buffer
    audio_buffer_lock = threading.Lock()

    # Define a function to read the audio data in a separate thread
    def read_audio():
        while True:
            indata = stream.read(4096)
            timestamp = time.time()
            with audio_buffer_lock:
                audio_buffer.append((np.frombuffer(indata, dtype=np.int16), timestamp))

    # Start the audio reading thread
    audio_thread = threading.Thread(target=read_audio)
    audio_thread.start()


    while True:
        ret, frame = cap.read()
        if ret:
            timestamp = time.time()
            video_buffer.append((frame, timestamp))

            # Add the timestamp to the video frame
            timestamp_str = time.strftime("%H:%M:%S", time.gmtime(timestamp))
            cv2.putText(frame, timestamp_str, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            # Display the resulting frame
            cv2.imshow('frame', frame)

            # Print the timestamp of the current audio sample
            with audio_buffer_lock:
                if audio_buffer:
                    timestamp_str = time.strftime("%H:%M:%S", time.gmtime(audio_buffer[-1][1]))
                    print(f"Current audio timestamp: {timestamp_str}")

            # If 'r' is pressed, write the buffer to a file
            if cv2.waitKey(1) & 0xFF == ord('r'):
                height, width, _ = video_buffer[0][0].shape
                first_video_timestamp = video_buffer[0][1]  # Timestamp of the first video frame
                last_video_timestamp = video_buffer[-1][1]  # Timestamp of the last video frame
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')

                # Include the timestamp in the file name
                timestamp_str = str(int(time.time()))
                video_filename = 'temp_video_' + timestamp_str + '.mp4'
                audio_filename = 'temp_audio_' + timestamp_str + '.wav'
                combined_filename = 'combined_' + timestamp_str + '.mp4'

                out = cv2.VideoWriter(video_filename, fourcc, frame_rate, (width, height))

                # Only write the most recent 10 seconds of frames to the file
                cutoff_time = time.time() - buffer_duration
                for frame, timestamp in video_buffer:
                    if timestamp >= cutoff_time:
                        out.write(frame)
                video_buffer = []
                print(f"Video buffer cleared at {time.time()}")  # Print the time when the video buffer is cleared

                # release the video writer
                out.release()

                # Save the audio to a file
                with audio_buffer_lock:
                    wf = wave.open(audio_filename, 'wb')
                    wf.setnchannels(channels)
                    wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
                    wf.setframerate(sample_rate)
                    # Only write audio samples that fall within the range of the video timestamps
                    for audio_data, timestamp in audio_buffer:
                        if first_video_timestamp <= timestamp <= last_video_timestamp:
                            wf.writeframes(audio_data.tobytes())
                    wf.close()
                    audio_buffer = []
                    print(f"Audio buffer cleared at {time.time()}")  # Print the time when the audio buffer is cleared

                # Convert the audio file to .mp3 using ffmpeg
                os.system(f'ffmpeg -i {audio_filename} {audio_filename.replace(".wav", ".mp3")}')

                # delay
                time.sleep(1)

                # Combine the audio and video using ffmpeg
                os.system(
                    f'ffmpeg -i {video_filename} -i {audio_filename.replace(".wav", ".mp3")} -c:v copy -c:a aac {combined_filename}')

                # Delete the temporary audio and video files
                os.remove(video_filename)
                os.remove(audio_filename.replace(".wav", ".mp3"))

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
    stream.stop_stream()
    stream.close()
    p.terminate()

    # Stop the audio reading thread
    audio_thread.join()

# Record to the buffer
record_to_buffer(buffer_duration)