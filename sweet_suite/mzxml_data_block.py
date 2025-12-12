import pybase64


class MzxmlDataBlock:
    """Represents a single scan block extracted from an mzXML file.

    A data block corresponds to one '<scan>' element in an mzXML file.
    It contains metadata such as retention time, compression type,
    byte order, and encoding precision, as well as the encoded MS data.

    Attributes:
        contents (str): Raw XML contents of the scan block.
        retention_time (float): Retention time of the scan in seconds.
        compression (bool): Whether the data is compressed (zlib).
        byte_order (str): Byte order of the encoded data ('little' or 'big').
        encoding_precision (int): Encoding precision in bits (32 or 64).
        decoded_data (dict): A dictionary containing base64-decoded MS data in 
            binary format, compression (bool), endian and encoding precision.
    """

    def __init__(self, contents: str):
        """Initialize a data block from its XML contents.

        Args:
            contents: Raw XML string representing a '<scan>' element.
        """
        self.contents = contents
        self.retention_time = self.get_retention_time()
        self.compression = self.get_compression()
        self.byte_order = self.get_byte_order()
        self.encoding_precision = self.get_encoding_precision()
        self.decoded_data = self.get_decoded_data()
        # Free up memory.
        self.contents = None

    def get_retention_time(self) -> float:
        """Return the retention time in seconds."""
        rt = (
            self.contents.split("retentionTime")[1]
            .split("\"")[1]
            [2:-1]  # e.g., "PT12.345S" -> "12.345"
        )
        return float(rt)

    def get_compression(self) -> bool:
        """Return whether the MS data is compressed."""
        return "compressionType=\"zlib\"" in self.contents

    def get_byte_order(self) -> str:
        """Return the byte order."""
        return self.contents.split("byteOrder")[1].split("\"")[1]

    def get_encoding_precision(self) -> int:
        """Return the encoding precision in bits (32 or 64)."""
        return int(self.contents.split("precision")[1].split("\"")[1])

    def get_decoded_data(self) -> dict:
        """Return a dictionary containing base64 decoded MS data in binary
        format, compression (bool), endian and encoding precision.
        """
        # Use pybase64 for decoding (C implementation of base64).
        encoded = self.contents.split('"m/z-int">')[1].split("</peaks>")[0]
        decoded = pybase64.b64decode(encoded)

        # Determine endian based on byte order.
        endian = "<" if self.byte_order == "little" else ">"

        # Determine encoding precision for NumPy ('f4' or 'f8').
        if self.encoding_precision == 64:
            precision = "8"
        elif self.encoding_precision == 32:
            precision = "4"
        else:
            # Fallback: attempt to parse as 32-bit if unexpected value.
            precision = "4"
        
        return {
            "bytes": decoded,
            "compression": self.compression,
            "endian": endian,
            "precision": precision
        }
