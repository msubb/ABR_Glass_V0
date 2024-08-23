import cv2
import sounddevice as sd
from scipy.io.wavfile import write
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips

# Set the duration and sample rate
duration = 10  # seconds
sample_rate = 44100

cap = cv2.VideoCapture(0)

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# Print the resolution
print(f'Resolution: {width}x{height}')

writer = cv2.VideoWriter('basicvideo.mkv', cv2.VideoWriter_fourcc(*'X264'), 20, (width,height))

# Start recording audio
audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=2)

while True:
    ret, frame = cap.read()

    writer.write(frame)

    cv2.imshow('frame', frame)

    if cv2.waitKey(1) & 0xFF == 27:
        break

# Wait for the recording to finish
sd.wait()

# Save the audio to a .wav file
write('output.wav', sample_rate, audio)

cap.release()
writer.release()
cv2.destroyAllWindows()

# Combine audio and video
videoclip = VideoFileClip('basicvideo.mkv')
audioclip = AudioFileClip('output.wav')

videoclip.audio = audioclip
videoclip.write_videofile('final_output.mp4')