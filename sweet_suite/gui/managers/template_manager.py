import os
import shutil

from PyQt6.QtWidgets import QFileDialog

from ..ui.ui_helpers import UIHelpers
from ...utils import utils


class TemplateManager:
    """Copy packaged alignment, analyte, and block templates for the user.

    The manager prompts for a destination and reports whether the selected
    template was copied successfully.
    """
    
    TEMPLATES = {
        "lc_ms_alignment": (
            "lc_ms_alignment_template.xlsx", "LC-MS alignment template"
        ),
        "ms_analytes": ("ms_analytes_template.xlsx", "(LC-)MS analytes template"),
        "lc_fld_alignment": (
            "lc_fld_alignment_template.xlsx", "LC-FLD alignment template"
        ),
        "lc_fld_peaks": ("lc_fld_peaks_template.xlsx", "LC-FLD peaks template"),
        "block": ("template.block", "Block template")
    }
    
    def __init__(self, parent):
        """Initialize template manager. 
        
        Args:
            parent: Parent widget (MainWindow).
        """
        self.parent = parent
    
    def download_template(self, template_type: str) -> None:
        """Download a template file.
        
        Args:
            template_type: One of 'lc_ms_alignment', 'ms_analytes',
                'lc_fld_alignment', 'lc_fld_peaks' or 'block'.
        """
        if template_type not in self.TEMPLATES:
            raise ValueError(f"Unknown template type: {template_type}")
        
        filename, display_name = self.TEMPLATES[template_type]
        template_location = utils.resource_path(os.path.join(
            "sweet_suite", "resources", "templates", filename
        ))
        
        folder = QFileDialog.getExistingDirectory(
            self.parent, f"Select folder to save {display_name}"
        )
        
        if folder:
            save_path = os.path.join(folder, filename)
            try:
                shutil.copyfile(template_location, save_path)
                UIHelpers.show_message_box(
                    self.parent,
                    title="Template saved",
                    text=f"{display_name} saved to:",
                    informative_text=save_path,
                    icon="Information"
                )
            except Exception as e:
                UIHelpers.show_message_box(
                    self.parent,
                    title="Error saving template",
                    text=f"Could not save {display_name.lower()}.",
                    informative_text=str(e),
                    icon="Critical"
                )
