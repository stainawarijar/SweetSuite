import glob
import os

from ...resources.constants import ISOTOPES
from ..ui.ui_helpers import UIHelpers


class BlockParser:
    """Handles parsing and validation of block files."""
    
    def __init__(self, parent, ui):
        """Initialize block parser. 
        
        Args:
            parent: Parent widget (MainWindow).
            ui: Main window UI object.
        """
        self.parent = parent
        self.ui = ui
    
    def parse_blocks(self) -> dict:
        """Loop over all block files in the specified directory, and creates
        a dictionary containing a dictionary for each block.
        
        Returns:
            Dictionary of block data, or None if error occurs.
        
        Raises a warning message if there are no block files. 
        """
        try:
            blocks_dict = {}
            blocks_path = self.ui.path_blocks.item(0).text()
            files = glob.glob(os.path.join(blocks_path, "*.block"))
            
            for filename in files:
                block = os.path.splitext(os.path.basename(filename))[0]
                keys, values = [], []
                skip_block = False  # Flag to indicate skipping of block file. 
                
                with open(filename, "r") as f:
                    for line in f.readlines():
                        # Ignore comments and empty lines.
                        if line.strip().startswith("#") or line.strip() == "":
                            continue
                        
                        # Extract key-value pair and key.
                        kv = line.rstrip().split(":")
                        key = kv[0].strip()
                        
                        # In case of element, check if it is known.
                        if key not in ["mass", "charge"] and key[:-1] not in ISOTOPES.keys():
                            UIHelpers.show_message_box(
                                self.parent,
                                title="Incorrectly formatting of block file",
                                text=f"Block file '{block}' contains an unknown element '{key}'.",
                                informative_text="Adjust the file, or it cannot be used.",
                                icon="Warning"
                            )
                            skip_block = True
                            break
                        
                        try:
                            values.append(int(kv[1].strip()))
                            keys.append(key)
                        except ValueError:
                            try:
                                values.append(float(kv[1].strip()))
                                keys.append(key)
                            except ValueError:
                                UIHelpers.show_message_box(
                                    self.parent,
                                    title="Error in parsing block file",
                                    text=f"'{key}' in block file '{block}' is not a number.",
                                    informative_text="Adjust the file, or it cannot be used.",
                                    icon="Warning"
                                )
                                skip_block = True
                                break
                
                if not skip_block:
                    blocks_dict[block] = dict(zip(keys, values))
            
            # Check if each block contains at least a mass. 
            incorrect = []
            for name, vals in blocks_dict.items():
                if "mass" not in vals.keys():
                    UIHelpers.show_message_box(
                        self.parent,
                        title="Missing mass",
                        text=f"Block file '{name}' contains no mass.",
                        informative_text="Adjust the file, or it cannot be used.",
                        icon="Warning"
                    )
                    incorrect.append(name)
            for name in incorrect:
                blocks_dict.pop(name)
            
            if len(blocks_dict) == 0:
                UIHelpers.show_message_box(
                    self.parent,
                    title="Empty blocks directory",
                    text=(
                        "The specified blocks directory does not contain any"
                        " '.block' files."
                    ),
                    informative_text="",
                    icon="Warning"
                )
            
            return blocks_dict
        
        except Exception as e:
            UIHelpers.show_message_box(
                self.parent,
                title="Unexpected error",
                text=(
                    "An unexpected error occurs while parsing the blocks"
                    " directory:"
                ),
                informative_text=str(e),
                icon="Critical"
            )
            return None
    
    def update_charge_carriers(self) -> None:
        """Fill in the options for charge carriers based on the blocks."""
        # Update the blocks based on current folder. 
        blocks_dict = self.parse_blocks()
        self.parent.blocks = blocks_dict
        
        if blocks_dict is None:
            return
        
        try:
            # Collect charge carriers as (name, charge). 
            charge_carriers = []
            for name, vals in blocks_dict.items():
                if not isinstance(vals["charge"], int):
                    UIHelpers.show_message_box(
                        self.parent,
                        title="Non-integer charge",
                        text=f"Block {name} has a non-integer charge.",
                        informative_text="Adjust the file.",
                        icon="Warning"
                    )
                elif vals["charge"] != 0:
                    charge_carriers.append((name, vals["charge"]))
            
            # Create selection options.
            options = []
            for name, charge in charge_carriers:
                if charge > 0:
                    options.append(f"{name} ({charge}+)")
                else:
                    options.append(f"{name} ({abs(charge)}-)")
            
            # Move proton to the front if present. 
            for option in options:
                if option.startswith("proton"):
                    options.remove(option)
                    options.insert(0, option)
                    break
            
            self.ui.comboBox_charge_carrier.clear()
            self.ui.comboBox_charge_carrier.addItems(options)
            
            if len(options) == 0:
                UIHelpers.show_message_box(
                    self.parent,
                    title="Missing charge carriers",
                    text=(
                        "The specified blocks directory does not contain"
                        " any charge carriers."
                    ),
                    informative_text="",
                    icon="Warning"
                )
        
        except Exception as e:
            UIHelpers.show_message_box(
                self.parent,
                title="Unexpected error",
                text=(
                    "An unexpected error occured while determining potential"
                    "charge carriers:"
                ),
                informative_text=str(e),
                icon="Critical"
            )