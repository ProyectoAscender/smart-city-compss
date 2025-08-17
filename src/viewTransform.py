import numpy as np
import cv2

class ViewTransformer:
    def __init__(self, pmatPath: str) -> None:
        self.M = np.loadtxt(pmatPath,  delimiter=' ', usecols=range(3))
        
    def transform_points(self, points: np.ndarray) -> np.ndarray:
        if points.size == 0:
            return points
        
        reshaped_points = points.reshape(-1, 1, 2).astype(np.float32)
        transformed_points = cv2.perspectiveTransform(reshaped_points, self.m)
        return transformed_points.reshape(-1, 2)
    
    def pixel_to_map(self, pixel):
        """
        Convert a set of pixel coordinates to map coordinates
        Parameters
        ----------
        pixel : (N,2) numpy array or (x,y) tuple
            The (x,y) pixel coordinates to be converted
        Returns
        -------
        (N,2) numpy array
            The corresponding map coordinates
        """
        if type(pixel) != np.ndarray:
            pixel = np.array(pixel).reshape(1,2)
        assert pixel.shape[1]==2, "Need (N,2) input array" 
        pixel = np.concatenate([pixel, np.ones((pixel.shape[0],1))], axis=1)
        mapPoints = np.dot(self.M,pixel.T)
        # cv2.perspectiveTransform(pixel[0][0:2].reshape(-1, 1, 2).astype(np.float32), self.M)
        
        return (mapPoints[:2,:]/mapPoints[2,:]).T

