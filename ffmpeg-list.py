import subprocess

command = ['ffmpeg', '-f', 'avfoundation', '-list_devices', 'true', '-i', '']

subprocess.run(command)