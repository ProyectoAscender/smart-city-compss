import cv2
import numpy as np

gst_out = (
    "appsrc ! videoconvert ! x264enc tune=zerolatency bitrate=500 speed-preset=ultrafast ! "
    "rtph264pay config-interval=1 pt=96 ! "
    "udpsink host=127.0.0.1 port=6000"
)

frame_size = (640, 480)
fps = 1

print("GStreamer pipeline usado:")
print(gst_out)

writer = cv2.VideoWriter(gst_out, cv2.CAP_GSTREAMER, 0, fps, frame_size, True)

if not writer.isOpened():
    print("🚨 NO se pudo abrir el VideoWriter.")
    exit(1)

for i in range(100):
    frame = np.full((480, 640, 3), (i * 2 % 255, 50, 100), dtype=np.uint8)
    writer.write(frame)
    print(f"Escribiendo frame {i}")

writer.release()