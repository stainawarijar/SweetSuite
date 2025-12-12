import os

import numpy as np


class SumSpectrum:
    """Represents a summed mass spectrum over a retention time range.

    A `SumSpectrum` object stores the combined spectrum created from
    multiple scans within a defined retention time window. It provides
    access to the underlying m/z-intensity data and supports exporting
    the spectrum to a `.xy` file.

    Attributes:
        file_raw (str): Name of the file (mzXML or mzXML) from which the 
            raw data originates, excluding file extension.
        time (float): Center of the retention time window.
        time_window (float): Half-width of the retention time range around
            the center.
        data (np.ndarray): 2D array with two columns: m/z values (float) and
            intensities (float).
        name (str): Generated identifier for the sum spectrum, formatted as
            `SumSpectrum_<time>_<time_window>_<mzxml_file>`.
    """

    def __init__(
        self,
        file_raw: str,
        time: float,
        time_window: float,
        data: np.ndarray,
    ):
        """Initialize a summed spectrum.

        Args:
            file_raw: Name of the file (mzXML or mzXML) from which the raw data 
                originates, excluding file extension,
            time: Center of the retention time window.
            time_window: Half-width of the retention time range around the 
                center.
            data: 2D NumPy array with m/z values in the first column and 
                intensities in the second column.
        """
        self.file_raw = file_raw
        self.time = time
        self.time_window = time_window
        self.data = data
        self.name = self.get_name()

    def get_name(self) -> str:
        """Generate a unique name for the sum spectrum.

        Returns:
            Name in the format `SumSpectrum_<time>_<time_window>_<file_raw>`.
        """
        return f"SumSpectrum_{self.time}_{self.time_window}_{self.file_raw}"

    def write_xy(self, path: str) -> None:
        """Write m/z values and intensities to a '.xy' file.

        The name of the '.xy' file will have the following format:
        `SumSpectrum_<time>_<time_window>_<mzxml_file>.xy`.
        The column with m/z values and the column with intensities are
        separated by a tab.

        Args:
            path: Path to the directory in which the '.xy' file is saved.
        """
        # Set filename and path to the file.
        full_path = os.path.join(path, f"{self.name}.xy")
        
        # Write to file, round numbers to 8 decimals.
        np.savetxt(full_path, self.data, delimiter="\t", fmt="%.8f")
