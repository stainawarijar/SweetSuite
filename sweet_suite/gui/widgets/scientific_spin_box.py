from PyQt6.QtWidgets import QDoubleSpinBox


class ScientificSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox subclass that displays and parses values in 
    scientific notation.
    """
    def textFromValue(self, value: float) -> str:
        """Return the string representation of the given value in scientific
        notation, rounded to three decimals.
        """
        return "{:.3e}".format(value)
    
    def valueFromText(self, text: str) -> float:
        """Parse the input text as a float. Returns 0.0 if the text cannot
        be converted.
        """
        try:
            return float(text)
        except ValueError:
            return 0.0