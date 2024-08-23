import subprocess

command = ['ffmpeg', '-framerate', '59.940180', '-f', 'avfoundation', '-video_size', '640x480', '-framerate', '30', '-i', '0:3', '-r', '30', 'output.mkv']

subprocess.run(command)

