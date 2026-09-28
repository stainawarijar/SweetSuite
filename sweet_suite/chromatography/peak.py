import numpy as np


class Peak:
    """Represents a chromatographic peak.
    """
    def __init__(
        self,
        data: np.ndarray,
        integration_window: float
    ):
        self.data = data
        self.integration_window = integration_window

