import uuid
import requests
import cv2
import numpy as np
import time

BASE_URL = "http://10.8.170.59:8000"

while True:
    try:
        cycle_id = uuid.uuid4().hex

        # Trigger capture
        r = requests.post(
            f"{BASE_URL}/camera/captures/{cycle_id}",
            timeout=10
        )
        r.raise_for_status()

        # Download image
        r = requests.get(
            f"{BASE_URL}/camera/captures/{cycle_id}",
            timeout=10
        )
        r.raise_for_status()

        # Convert JPEG bytes to OpenCV image
        img = cv2.imdecode(
            np.frombuffer(r.content, np.uint8),
            cv2.IMREAD_COLOR
        )

        if img is not None:
            cv2.imshow("Camera", img)

        # Press q to quit
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    except Exception as e:
        print(e)
        time.sleep(0.5)

cv2.destroyAllWindows()