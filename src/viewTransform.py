import numpy as np
import cv2

class ViewTransformer:
    def __init__(self, pmatPath: str) -> None:
        self.m = np.loadtxt(pmatPath,  delimiter=' ', usecols=range(3))
        
    def transform_points(self, points: np.ndarray) -> np.ndarray:
        if points.size == 0:
            return points
        
        reshaped_points = points.reshape(-1, 1, 2).astype(np.float32)
        transformed_points = cv2.perspectiveTransform(reshaped_points, self.m)
        return transformed_points.reshape(-1, 2)

