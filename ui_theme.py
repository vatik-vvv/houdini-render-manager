"""Shared dark theme and queue UI colors."""
import base64

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

TOGGLE_ON_COLOR = QColor(76, 175, 80)
TOGGLE_OFF_COLOR = QColor(211, 47, 47)
PROGRESS_FILL_COLOR = QColor(76, 175, 80)

_CHECKBOX_CHECK_URI = (
    "data:image/svg+xml;base64,"
    + base64.b64encode(
        b'<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">'
        b'<path fill="none" stroke="#6ec26e" stroke-width="2.2" stroke-linecap="round" '
        b'stroke-linejoin="round" d="M3 7l3 3 5-6"/></svg>'
    ).decode("ascii")
)

STATUS_STYLES = {
    "Queued": (QColor(70, 70, 70), QColor(220, 220, 220)),
    "Running": (QColor(25, 60, 95), QColor(200, 230, 255)),
    "Completed": (QColor(27, 60, 40), QColor(200, 255, 210)),
    "Skipped": (QColor(55, 55, 30), QColor(230, 230, 180)),
    "Stopped": (QColor(80, 45, 20), QColor(255, 210, 170)),
    "Failed": (QColor(70, 25, 25), QColor(255, 200, 200)),
}


def apply_dark_theme(widget):
    widget.setStyleSheet(
        f"""
    QWidget, QMainWindow, QDialog {{
        background-color: #353535;
        color: #ffffff;
    }}
    QLineEdit, QTextEdit, QListWidget, QTableView, QTableWidget, QComboBox {{
        background-color: #191919;
        color: #ffffff;
        border: 1px solid #555555;
    }}
    QPushButton {{
        background-color: #353535;
        color: #ffffff;
        border: 1px solid #555555;
        padding: 5px 10px;
        border-radius: 3px;
    }}
    QPushButton:hover {{ background-color: #454545; }}
    QPushButton:pressed {{ background-color: #252525; }}
    QGroupBox {{
        color: #ffffff;
        border: 1px solid #555555;
        border-radius: 5px;
        margin-top: 10px;
        padding-top: 10px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 3px 0 3px;
    }}
    QLabel {{ color: #ffffff; }}
    QLabel#appTitleLabel {{
        font-size: 17px;
        font-weight: bold;
        letter-spacing: 2px;
        color: #e8e8e8;
    }}
    QLabel#workflowGuide {{
        color: #b8c0c8;
        font-size: 12px;
        padding: 4px 8px;
        background-color: #2a2a2a;
        border: 1px solid #484848;
        border-radius: 4px;
    }}
    QLabel#tgInstructions {{
        color: #c8d0d8;
        font-size: 12px;
        padding: 4px;
    }}
    QLabel#zoneHelpPanel {{
        color: #a8b0b8;
        font-size: 11px;
        padding: 6px;
        background-color: #2e2e2e;
        border: 1px solid #484848;
        border-radius: 4px;
    }}
    QCheckBox {{ color: #ffffff; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid #888888;
        border-radius: 3px;
        background-color: #2a2a2a;
    }}
    QCheckBox::indicator:hover {{ border-color: #aaaaaa; }}
    QCheckBox::indicator:checked {{
        background-color: #2a2a2a;
        border-color: #6ec26e;
        image: url({_CHECKBOX_CHECK_URI});
    }}
    QHeaderView::section {{
        background-color: #353535;
        color: #ffffff;
        padding: 5px;
        border: 1px solid #555555;
    }}
    QListWidget::item:selected,
    QTableView::item:selected,
    QTableWidget::item:selected {{
        background-color: #5a4a72;
        color: #ffffff;
        border: 1px solid #8e2dc5;
    }}
    QTableView, QTableWidget {{
        gridline-color: #404040;
        alternate-background-color: #1e1e1e;
    }}
    QTableView::item, QTableWidget::item {{ padding: 2px 6px; }}
    QSplitter::handle:vertical {{ background: #3a3a3a; }}
    QSplitter::handle:vertical:hover {{ background: #4a4a4a; }}
    """
    )

