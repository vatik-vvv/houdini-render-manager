"""Shared dark theme and queue UI colors."""
from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QStyle,
    QStyleOptionButton,
)

TOGGLE_ON_COLOR = QColor(76, 175, 80)
TOGGLE_OFF_COLOR = QColor(211, 47, 47)
CHECKBOX_INDICATOR_SIZE = 18

STATUS_STYLES = {
    "Queued": (QColor(70, 70, 70), QColor(220, 220, 220)),
    "Running": (QColor(25, 60, 95), QColor(200, 230, 255)),
    "Completed": (QColor(27, 60, 40), QColor(200, 255, 210)),
    "Skipped": (QColor(55, 55, 30), QColor(230, 230, 180)),
    "Stopped": (QColor(80, 45, 20), QColor(255, 210, 170)),
    "Failed": (QColor(70, 25, 25), QColor(255, 200, 200)),
}


def paint_checkbox_indicator(painter, rect, checked, hovered=False, enabled=True):
    """Draw checkbox box + checkmark; QSS image: url() is unreliable on Windows."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if enabled:
        border = QColor("#6ec26e" if checked else "#aaaaaa" if hovered else "#888888")
        fill = QColor("#2a2a2a")
        check_color = QColor("#6ec26e")
    else:
        border = QColor("#555555")
        fill = QColor("#252525")
        check_color = QColor("#555555")

    box = QRect(rect)
    if box.width() > 2 and box.height() > 2:
        box = box.adjusted(1, 1, -1, -1)
    painter.setPen(QPen(border, 2))
    painter.setBrush(fill)
    painter.drawRoundedRect(box, 3, 3)

    if checked:
        pen = QPen(
            check_color,
            2.2,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(pen)
        x, y = rect.x(), rect.y()
        painter.drawLine(x + 4, y + 9, x + 7, y + 12)
        painter.drawLine(x + 7, y + 12, x + 14, y + 5)
    painter.restore()


class ThemedCheckBox(QCheckBox):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        style = self.style()
        indicator_rect = style.subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, opt, self)
        if indicator_rect.isEmpty():
            m = CHECKBOX_INDICATOR_SIZE
            indicator_rect = QRect(0, max(0, (self.height() - m) // 2), m, m)
        hovered = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        paint_checkbox_indicator(
            painter, indicator_rect, self.isChecked(), hovered, self.isEnabled()
        )

        text_rect = style.subElementRect(QStyle.SubElement.SE_CheckBoxContents, opt, self)
        opt.rect = text_rect
        text_color = QColor("#ffffff") if self.isEnabled() else QColor("#777777")
        opt.palette.setColor(QPalette.ColorRole.WindowText, text_color)
        style.drawControl(QStyle.ControlElement.CE_CheckBoxLabel, opt, painter, self)

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(max(hint.width(), CHECKBOX_INDICATOR_SIZE + 8), max(hint.height(), CHECKBOX_INDICATOR_SIZE))


def apply_dark_theme(widget):
    widget.setStyleSheet(
        """
    QWidget, QMainWindow, QDialog {
        background-color: #353535;
        color: #ffffff;
    }
    QLineEdit, QTextEdit, QListWidget, QTableView, QTableWidget, QComboBox {
        background-color: #191919;
        color: #ffffff;
        border: 1px solid #555555;
    }
    QPushButton {
        background-color: #353535;
        color: #ffffff;
        border: 1px solid #555555;
        padding: 5px 10px;
        border-radius: 3px;
    }
    QPushButton:hover { background-color: #454545; }
    QPushButton:pressed { background-color: #252525; }
    QGroupBox {
        color: #ffffff;
        border: 1px solid #555555;
        border-radius: 5px;
        margin-top: 10px;
        padding-top: 10px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 3px 0 3px;
    }
    QLabel { color: #ffffff; }
    QLabel#appTitleLabel {
        font-size: 17px;
        font-weight: bold;
        letter-spacing: 2px;
        color: #e8e8e8;
    }
    QLabel#workflowGuide {
        color: #b8c0c8;
        font-size: 12px;
        padding: 4px 8px;
        background-color: #2a2a2a;
        border: 1px solid #484848;
        border-radius: 4px;
    }
    QLabel#tgInstructions {
        color: #c8d0d8;
        font-size: 12px;
        padding: 4px;
    }
    QLabel#zoneHelpPanel {
        color: #a8b0b8;
        font-size: 11px;
        padding: 6px;
        background-color: #2e2e2e;
        border: 1px solid #484848;
        border-radius: 4px;
    }
    ThemedCheckBox { color: #ffffff; spacing: 8px; }
    ThemedCheckBox::indicator {
        width: 18px;
        height: 18px;
        border: none;
        background: transparent;
    }
    QHeaderView::section {
        background-color: #353535;
        color: #ffffff;
        padding: 5px;
        border: 1px solid #555555;
    }
    QListWidget::item:selected,
    QTableView::item:selected,
    QTableWidget::item:selected {
        background-color: #5a4a72;
        color: #ffffff;
        border: 1px solid #8e2dc5;
    }
    QTableView, QTableWidget {
        gridline-color: #404040;
        alternate-background-color: #1e1e1e;
    }
    QTableView::item, QTableWidget::item { padding: 2px 6px; }
    QSplitter::handle:vertical { background: #3a3a3a; }
    QSplitter::handle:vertical:hover { background: #4a4a4a; }
    """
    )
