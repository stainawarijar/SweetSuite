import os
import shutil

from PyQt6.QtWidgets import QFileDialog

from ..ui.ui_helpers import UIHelpers
from ...utils import utils


class TemplateManager:
    """Handles template file download operations."""
    
    TEMPLATES = {
        "alignment": ("alignment_template.xlsx", "Alignment template"),
        "analytes": ("analytes_template.xlsx", "Analytes template"),
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
            template_type: Type of template ('alignment', 'analytes', or 'block')
        """
        if template_type not in self.TEMPLATES:
            raise ValueError(f"Unknown template type: {template_type}")
        
        filename, display_name = self.TEMPLATES[template_type]
        template_location = utils.resource_path(os.path.join(
            "sweet_suite", "resources", "templates", filename
        ))
        
        folder = QFileDialog.getExistingDirectory(
            self.parent, f"Select folder to save {display_name.lower()}"
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
                    self. parent,
                    title="Error saving template",
                    text=f"Could not save {display_name.lower()}.",
                    informative_text=str(e),
                    icon="Critical"
                )