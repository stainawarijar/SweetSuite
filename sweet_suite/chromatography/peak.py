import logging

import numpy as np


class Peak:
    """Represents a chromatographic peak in an LC-FLD chromatogram.
    """
    def __init__(
        self,
        data: np.ndarray,
        integration_window: float
    ):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.data = data
        self.integration_window = integration_window

