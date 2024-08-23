import cv2

# Open the default camera
cap = cv2.VideoCapture(0)

# Check if camera opened successfully
if not cap.isOpened():
    print("Error opening video capture")
    exit()

# Create a VideoWriter object to save the video
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter('test.mp4', fourcc, 20.0, (640, 480))

while True:
    # Read frame from camera
    ret, frame = cap.read()

    if not ret:
        print("Error reading video frame")
        break

    # Display the resulting frame
    cv2.imshow('Preview', frame)

    # Save the frame to the video file
    out.write(frame)

    # Break the loop on 'q' key press
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release the video capture and writer objects
cap.release()
out.release()

# Close all OpenCV windows
cv2.destroyAllWindows()