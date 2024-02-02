import cv2

def list_capture_devices(max_devices=10):
    devices = []
    for index in range(max_devices):
        cap = cv2.VideoCapture(index)
        if cap is None or not cap.isOpened():
            cap.release()
        else:
            devices.append(index)
            cap.release()
    return devices

print(list_capture_devices())