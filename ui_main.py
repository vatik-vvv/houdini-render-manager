# -*- coding: utf-8 -*-
import glob, os, json, re, subprocess, requests, sys
from datetime import datetime
from render_runner import run_render, stop_render
from telegram_notifier import send_image
from app_paths import config_path, bundled_script, app_icon_path, find_bundled_file, hython_script_path
from path_utils import (
    norm_path_key,
    resolve_houdini_vars,
    expand_frame_in_path,
    normalize_output_template,
    path_tooltip,
)
from PySide6.QtWidgets import (
      QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QComboBox,
      QFileDialog, QLabel, QDialog, QLineEdit, QTableWidget, QTableWidgetItem,
      QTextEdit, QCheckBox, QGroupBox, QApplication, QAbstractItemView, QSplitter,
      QSplitterHandle,
      QSizePolicy, QStyledItemDelegate, QStyle, QStyleOptionButton, QStyleOptionViewItem,
      QMessageBox, QMenu, QLineEdit, QSpinBox
  )
from PySide6.QtGui import QPalette, QColor, QIcon, QFont, QPainter, QPen, QPixmap
from PySide6.QtCore import Qt, QByteArray, QMimeData, QThread, Signal, QEvent, QRect, QSize

CONFIG_FILE = config_path()
HEADER_LOGO_HEIGHT_PX = 27
TOGGLE_ON_COLOR = QColor(76, 175, 80)
TOGGLE_OFF_COLOR = QColor(211, 47, 47)
QUEUE_COLUMN_KEYS = [
    "enabled", "hip", "rop", "type", "start_frame", "end_frame", "skip",
    "size_x", "size_y", "resize", "output_path", "status", "send2bot",
    "start_time", "end_time", "duration",
]
COL_HIP, COL_ROP, COL_OUTPUT, COL_STATUS = 1, 2, 10, 11
FULL_PATH_ROLE = Qt.ItemDataRole.UserRole
RENDER_PROGRESS_ROLE = Qt.ItemDataRole.UserRole + 2
BASE_SIZE_X_ROLE = Qt.ItemDataRole.UserRole + 3
BASE_SIZE_Y_ROLE = Qt.ItemDataRole.UserRole + 4
STATUS_STYLES = {
    "Queued": (QColor(70, 70, 70), QColor(220, 220, 220)),
    "Running": (QColor(0, 120, 200), QColor(255, 255, 255)),
    "Completed": (QColor(46, 125, 50), QColor(255, 255, 255)),
    "Failed": (QColor(183, 28, 28), QColor(255, 255, 255)),
    "Skipped": (QColor(100, 100, 100), QColor(200, 200, 200)),
    "Stopped": (QColor(150, 100, 0), QColor(255, 255, 255)),
}


def resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
    return os.path.join(base_path, relative_path)

# Translation dictionary
TRANSLATIONS = {
    "en": {
        "title": "Houdini Render Manager",
        "zone1": "1 - Check Houdini Environment",
        "houdini_version": "Houdini Version:",
        "browse": "Browse",
        "save_settings": "Save Settings",
        "check_env": "Check Environment",
        "telegram_settings": "Telegram Settings",
        "language": "Language",
        "zone2": "2 - Add HIP files",
        "hip_files": "HIP Files",
        "add_hip": "Add HIP",
        "remove_hip": "Remove HIP",
        "scan_for": "For scan:",
        "scan_for_none": "(click a HIP file)",
        "zone3": "3 - Scan for ROPs",
        "scan_hip": "Scan HIP",
        "scan_hint": "Use Scan HIP above to populate ROPs",
        "zone4": "4 - Select ROPs to add to render queue",
        "found_nodes": "Found Render Nodes",
        "redshift": "Redshift",
        "karma": "Karma",
        "other": "Other",
        "add_queue": "Add to Render Queue",
        "zone5": "5 - Render Queue",
        "start_render": "Start Render",
        "stop_render": "Stop Render",
        "reset_rop": "Reset ROP",
        "remove_rop": "Remove ROP",
        "clear_log": "Clear log",
        "queue_headers": ["Enabled","HIP","ROP","Type","Start","End","Skip","Size X","Size Y","Resize","Output","Status","Send2Bot every","Start Time","End Time","Duration"],
        "bot_token": "Bot Token:",
        "chat_id": "Chat ID:",
        "save": "Save",
        "check_bot": "Check Bot",
        "send_test": "Send Test Message",
        "tg_saved": "Telegram settings saved.",
        "tg_preview_max": "Preview max side (px):",
        "tg_preview_hint": "Frames are converted to JPEG and resized (longest side). Supports PNG, JPG, TIF, EXR.",
        "render_progress_idle": "",
        "render_progress": "Render {cur}/{total}: {hip} → {rop} [{status}]",
        "enable_all": "Enable all",
        "disable_all": "Disable all",
        "open_hip": "Open HIP",
        "open_output": "Open output folder",
        "duplicate": "Duplicate",
        "duplicate_rop": "Already in queue: {rop} ({hip})",
        "rop_count": "Shown: {shown} / {total}",
        "add_all_rops": "Add all visible",
        "confirm_stop_title": "Stop render?",
        "confirm_stop_text": "Stop the current render and remaining queue?",
        "ctx_reset_status": "Reset status",
        "ctx_enable": "Enable",
        "ctx_disable": "Disable",
        "ctx_duplicate": "Duplicate",
        "ctx_reset": "Reset from HIP",
        "ctx_remove": "Remove from queue",
        "ctx_open_hip": "Open HIP",
        "ctx_open_output": "Open output folder",
        "path_empty": "Output path is empty — set it in the queue or rescan the ROP.",
        "splitter_queue_resize": "Drag to resize the render queue height (zone 5)",
    },
    "ru": {
        "title": "Менеджер рендера Houdini",
        "zone1": "1 - Проверка окружения Houdini",
        "houdini_version": "Версия Houdini:",
        "browse": "Обзор",
        "save_settings": "Сохранить параметры",
        "check_env": "Проверить окружение",
        "telegram_settings": "Параметры Telegram",
        "language": "Язык",
        "zone2": "2 - Добавить HIP файлы",
        "hip_files": "HIP файлы",
        "add_hip": "Добавить HIP",
        "remove_hip": "Удалить HIP",
        "scan_for": "Для скана:",
        "scan_for_none": "(выберите HIP файл)",
        "zone3": "3 - Сканирование ROPs",
        "scan_hip": "Сканировать HIP",
        "scan_hint": "Используйте Scan HIP выше для заполнения ROPs",
        "zone4": "4 - Выберите ROPs для добавления в очередь рендера",
        "found_nodes": "Найденные узлы рендера",
        "redshift": "Redshift",
        "karma": "Karma",
        "other": "Другое",
        "add_queue": "Добавить в очередь рендера",
        "zone5": "5 - Очередь рендера",
        "start_render": "Начать рендер",
        "stop_render": "Остановить рендер",
        "reset_rop": "Сбросить ROP",
        "remove_rop": "Удалить ROP",
        "clear_log": "Очистить лог",
        "queue_headers": ["Вкл.","HIP","ROP","Тип","Начало","Конец","Пропуск","Размер X","Размер Y","Масштаб","Путь вывода","Статус","Send2Bot every","Время начала","Время окончания","Длительность"],
        "bot_token": "Токен бота:",
        "chat_id": "ID чата:",
        "save": "Сохранить",
        "check_bot": "Проверить бота",
        "send_test": "Отправить тестовое сообщение",
        "tg_saved": "Настройки Telegram сохранены.",
        "tg_preview_max": "Макс. сторона превью (px):",
        "tg_preview_hint": "Кадры конвертируются в JPEG с уменьшением (длинная сторона). Форматы: PNG, JPG, TIF, EXR.",
        "render_progress_idle": "",
        "render_progress": "Рендер {cur}/{total}: {hip} → {rop} [{status}]",
        "enable_all": "Включить все",
        "disable_all": "Выключить все",
        "open_hip": "Открыть HIP",
        "open_output": "Папка вывода",
        "duplicate": "Дублировать",
        "duplicate_rop": "Уже в очереди: {rop} ({hip})",
        "rop_count": "Показано: {shown} / {total}",
        "add_all_rops": "Добавить все видимые",
        "confirm_stop_title": "Остановить рендер?",
        "confirm_stop_text": "Остановить текущий рендер и оставшиеся задачи в очереди?",
        "ctx_reset_status": "Сбросить статус",
        "ctx_enable": "Включить",
        "ctx_disable": "Выключить",
        "ctx_duplicate": "Дублировать",
        "ctx_reset": "Сбросить из HIP",
        "ctx_remove": "Удалить из очереди",
        "ctx_open_hip": "Открыть HIP",
        "ctx_open_output": "Папка вывода",
        "path_empty": "Путь вывода пуст — укажите в очереди или пересканируйте ROP.",
        "splitter_queue_resize": "Потяните разделитель, чтобы изменить высоту очереди рендера (зона 5)",
    }
}


class GripSplitterHandle(QSplitterHandle):
    """Splitter grips: flat under zone 1, queue grips above/below zone 5."""

    STYLE_NORMAL = 0
    STYLE_QUEUE = 1
    STYLE_FLAT = 2

    QUEUE_HEIGHT = 8
    NORMAL_HEIGHT = 5
    FLAT_HEIGHT = 2

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self._style = self.STYLE_NORMAL
        self._apply_cursor()

    def set_style(self, style):
        self._style = style
        self._apply_cursor()
        self.update()

    def _apply_cursor(self):
        if not self.isEnabled() or self._style == self.STYLE_FLAT:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif self.orientation() == Qt.Orientation.Vertical:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeHorCursor)

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self._apply_cursor()

    def sizeHint(self):
        if self.orientation() == Qt.Orientation.Vertical:
            if self._style == self.STYLE_QUEUE:
                h = self.QUEUE_HEIGHT
            elif self._style == self.STYLE_FLAT:
                h = self.FLAT_HEIGHT
            else:
                h = self.NORMAL_HEIGHT
            return QSize(max(self.width(), 80), h)
        if self._style == self.STYLE_QUEUE:
            w = self.QUEUE_HEIGHT
        elif self._style == self.STYLE_FLAT:
            w = self.FLAT_HEIGHT
        else:
            w = self.NORMAL_HEIGHT
        return QSize(w, max(self.height(), 80))

    def paintEvent(self, event):
        p = QPainter(self)
        rect = self.rect()
        if self._style == self.STYLE_FLAT:
            p.fillRect(rect, QColor("#353535"))
            p.end()
            return
        p.fillRect(rect, QColor("#3a3a3a"))
        grip_color = QColor("#9e9e9e" if self._style == self.STYLE_QUEUE else "#707070")
        if self.orientation() == Qt.Orientation.Vertical:
            cy = rect.center().y()
            cx = rect.center().x()
            p.setPen(QPen(grip_color, 2))
            for offset in (-4, 0, 4):
                p.drawLine(cx - 28, cy + offset, cx + 28, cy + offset)
        else:
            cx = rect.center().x()
            cy = rect.center().y()
            p.setPen(QPen(grip_color, 2))
            for offset in (-4, 0, 4):
                p.drawLine(cx + offset, cy - 28, cx + offset, cy + 28)
        p.end()


class MainSplitter(QSplitter):
    """Render queue (zone 5) resizable via grips above and below it."""

    QUEUE_HANDLE_INDEXES = (0, 1)

    def createHandle(self):
        return GripSplitterHandle(self.orientation(), self)

    def configure_handles(self, queue_tooltip=""):
        for idx in range(self.count()):
            handle = self.handle(idx)
            if handle is None or not isinstance(handle, GripSplitterHandle):
                continue
            if idx in self.QUEUE_HANDLE_INDEXES:
                handle.set_style(GripSplitterHandle.STYLE_QUEUE)
                handle.setEnabled(True)
                if queue_tooltip:
                    handle.setToolTip(queue_tooltip)
            else:
                handle.set_style(GripSplitterHandle.STYLE_NORMAL)


def apply_status_style(item, status):
    if item is None:
        return
    colors = STATUS_STYLES.get(status)
    if colors:
        item.setBackground(colors[0])
        item.setForeground(colors[1])


def format_duration_hms(start_s, end_s):
    if not start_s or not end_s:
        return "--"
    try:
        t0 = datetime.strptime(start_s.strip(), "%H:%M:%S")
        t1 = datetime.strptime(end_s.strip(), "%H:%M:%S")
        delta = int((t1 - t0).total_seconds())
        if delta < 0:
            delta += 24 * 3600
        m, sec = divmod(delta, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m}:{sec:02d}"
    except ValueError:
        return "--"

def apply_dark_theme(widget):
    """Apply dark theme with hard-coded colors"""
    stylesheet = """
    QWidget, QMainWindow, QDialog {
        background-color: #353535;
        color: #ffffff;
    }
    QLineEdit, QTextEdit, QListWidget, QTableWidget, QComboBox {
        background-color: #191919;
        color: #ffffff;
        border: 1px solid #555555;
    }
    QPushButton {
        background-color: #353535;
        color: #ffffff;
        border: 1px solid #555555;
        padding: 5px;
        border-radius: 3px;
    }
    QPushButton:hover {
        background-color: #454545;
    }
    QPushButton:pressed {
        background-color: #252525;
    }
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
    QLabel {
        color: #ffffff;
    }
    QLabel#appTitleLabel {
        font-size: 17px;
        font-weight: bold;
        letter-spacing: 2px;
        color: #e8e8e8;
    }
    QCheckBox {
        color: #ffffff;
    }
    QCheckBox::indicator {
        background-color: #191919;
        border: 1px solid #555555;
    }
    QCheckBox::indicator:checked {
        background-color: #8e2dc5;
    }
    QHeaderView::section {
        background-color: #353535;
        color: #ffffff;
        padding: 5px;
        border: 1px solid #555555;
    }
    QListWidget::item:selected {
        background-color: #5a4a72;
        color: #ffffff;
        border: 1px solid #8e2dc5;
    }
    QTableWidget::item:selected {
        background-color: #5a4a72;
        color: #ffffff;
        border: 1px solid #8e2dc5;
    }
    QSplitter::handle:vertical {
        background: #3a3a3a;
    }
    QSplitter::handle:vertical:hover {
        background: #4a4a4a;
    }
    """
    widget.setStyleSheet(stylesheet)


def normalize_toggle_value(raw_val, default="0"):
    if raw_val is None or raw_val == "":
        return default
    s = str(raw_val).lower()
    return "1" if s in ("true", "1", "yes") else "0"


def is_toggle_checked(item):
    if item is None:
        return False
    return normalize_toggle_value(item.data(Qt.UserRole), "0") == "1"


def apply_toggle_cell_style(item, checked):
    item.setData(Qt.UserRole, "1" if checked else "0")
    item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
    item.setBackground(TOGGLE_ON_COLOR if checked else TOGGLE_OFF_COLOR)
    item.setText("")
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)


def create_toggle_item(checked=True):
    item = QTableWidgetItem("")
    apply_toggle_cell_style(item, checked)
    return item


class FullPathEditDelegate(QStyledItemDelegate):
    """Open the line editor with the full stored path, not the shortened display text."""

    def __init__(self, table, on_committed=None):
        super().__init__(table)
        self.table = table
        self.on_committed = on_committed

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setMinimumWidth(400)
        return editor

    def setEditorData(self, editor, index):
        item = self.table.item(index.row(), index.column())
        if item:
            full = item.data(FULL_PATH_ROLE)
            editor.setText(str(full).strip() if full else item.text())

    def setModelData(self, editor, model, index):
        path = editor.text().strip()
        if self.on_committed:
            self.on_committed(index.row(), index.column(), path)


class StatusProgressDelegate(QStyledItemDelegate):
    """Status cell: opaque green fill left-to-right for active render progress."""

    def paint(self, painter, option, index):
        progress = index.data(RENDER_PROGRESS_ROLE)
        try:
            progress = max(0.0, min(1.0, float(progress))) if progress is not None else 0.0
        except (TypeError, ValueError):
            progress = 0.0

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        table = opt.widget
        item = table.item(index.row(), index.column()) if table else None

        rect = opt.rect
        if item:
            painter.fillRect(rect, item.background())
        else:
            style = opt.widget.style() if opt.widget else QApplication.style()
            style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, opt.widget)

        if progress > 0:
            fill_w = max(0, int(rect.width() * progress))
            painter.fillRect(rect.x(), rect.y(), fill_w, rect.height(), TOGGLE_ON_COLOR)

        style = opt.widget.style() if opt.widget else QApplication.style()
        opt.textElideMode = Qt.TextElideMode.ElideRight
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)


class ToggleCheckBoxDelegate(QStyledItemDelegate):
    def __init__(self, table, on_toggled=None):
        super().__init__(table)
        self.table = table
        self.on_toggled = on_toggled

    def paint(self, painter, option, index):
        item = self.table.item(index.row(), index.column())
        if item:
            painter.fillRect(option.rect, item.background())
        style = option.widget.style() if option.widget else QApplication.style()
        checkbox_opt = QStyleOptionButton()
        checkbox_opt.state = QStyle.StateFlag.State_Enabled
        if item and is_toggle_checked(item):
            checkbox_opt.state |= QStyle.StateFlag.State_On
        indicator_size = style.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, checkbox_opt, option.widget)
        checkbox_opt.rect = QRect(
            option.rect.x() + (option.rect.width() - indicator_size) // 2,
            option.rect.y() + (option.rect.height() - indicator_size) // 2,
            indicator_size,
            indicator_size,
        )
        style.drawControl(QStyle.ControlElement.CE_CheckBox, checkbox_opt, painter, option.widget)

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            item = self.table.item(index.row(), index.column())
            if item:
                apply_toggle_cell_style(item, not is_toggle_checked(item))
                if self.on_toggled:
                    self.on_toggled()
                return True
        return False

def set_disabled_style(btn):
  btn.setStyleSheet("QPushButton:disabled { background-color: #555; color: #aaa; }")

def set_next_style(btn):
  btn.setStyleSheet("QPushButton:enabled { background-color: #4CAF50; color: #fff; }")

def set_delete_style(btn):
  btn.setStyleSheet("QPushButton:enabled { background-color: #d32f2f; color: #fff; }")

def set_reset_style(btn):
  btn.setStyleSheet("QPushButton:enabled { background-color: #00BFFF; color: #fff; }")

class HipList(QListWidget):
  def __init__(self, parent=None):
      super().__init__(parent)
      self.setAcceptDrops(True)
      self.setSelectionMode(QAbstractItemView.ExtendedSelection)
      self.setAlternatingRowColors(True)

  def dragEnterEvent(self, event):
      if event.mimeData().hasUrls():
          event.acceptProposedAction()

  def dropEvent(self, event):
      event.acceptProposedAction()
      for url in event.mimeData().urls():
          path = url.toLocalFile()
          if path.lower().endswith(".hip"):
              self.addItem(path)
      parent = self.parent()
      if parent:
          if hasattr(parent, "on_hip_selection_changed"):
              parent.on_hip_selection_changed()
          if parent.hip_list.count() > 0:
              parent.hip_list.setCurrentRow(parent.hip_list.count() - 1)
              parent.update_hip_current_visual()
          if hasattr(parent, "save_state"):
              parent.save_state()

class RenderQueueTable(QTableWidget):
  def __init__(self, parent=None):
      super().__init__(parent)
      self.setDragDropMode(QAbstractItemView.InternalMove)
      self.setDefaultDropAction(Qt.DropAction.MoveAction)
      self.setSelectionBehavior(QAbstractItemView.SelectRows)
      self.setSelectionMode(QAbstractItemView.SingleSelection)
      self.setAlternatingRowColors(True)
      self.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
      self.parent_window = parent
      self.verticalHeader().setDefaultSectionSize(28)

  def data(self, index, role):
      if role == Qt.ItemDataRole.BackgroundRole and index.column() in (0, 6):
          item = self.item(index.row(), index.column())
          if item:
              return item.background()
      return super().data(index, role)

  def dragEnterEvent(self, event):
      if event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist"):
          event.acceptProposedAction()

  def dragMoveEvent(self, event):
      event.acceptProposedAction()

  def dropEvent(self, event):
      if event.source() is not self:
          event.ignore()
          return
      selected = self.selectedIndexes()
      if not selected:
          event.ignore()
          return

      src_row = selected[0].row()
      drop_index = self.indexAt(event.position().toPoint())
      dest_row = drop_index.row() if drop_index.isValid() else self.rowCount()
      if dest_row > self.rowCount():
          dest_row = self.rowCount()
      if src_row == dest_row or (src_row + 1 == dest_row and dest_row == self.rowCount()):
          event.accept()
          return

      parent = self.parent_window
      if not parent or not hasattr(parent, "_queue_row_to_entry"):
          event.ignore()
          return

      entry = parent._queue_row_to_entry(src_row)
      self.blockSignals(True)
      try:
          self.removeRow(src_row)
          if dest_row > src_row:
              dest_row -= 1
          self.insertRow(dest_row)
          parent._populate_queue_row(dest_row, entry=entry)
          self.selectRow(dest_row)
      finally:
          self.blockSignals(False)

      event.accept()
      if hasattr(self.parent_window, "save_state"):
          self.parent_window.save_state()

  def mousePressEvent(self, event):
      # Allow normal cell clicks and editing; deselect only when clicking empty area
      if event.button() == Qt.LeftButton:
          index = self.indexAt(event.pos())
          if not index.isValid():
              self.clearSelection()
      super().mousePressEvent(event)

class RenderQueueWorker(QThread):
  log_signal = Signal(str)
  update_row_signal = Signal(int, str, str, str)
  progress_signal = Signal(int, int, int)
  frame_progress_signal = Signal(int, float)
  finished_signal = Signal(bool)

  def __init__(self, queue_data, parent=None):
      super().__init__(parent)
      self.queue_data = queue_data

  def run(self):
      from datetime import datetime
      total = len(self.queue_data)
      for job_index, item in enumerate(self.queue_data, start=1):
          if self.isInterruptionRequested():
              break

          row = item["row"]
          self.progress_signal.emit(job_index, total, row)
          self.log_signal.emit(f"\n🎬 Рендер {job_index}/{total}: {os.path.basename(item['hip_file'])} | ROP: {item['rop_name']}")
          ax = max(1, int(item["size_x"] * item["resize_pct"] / 100))
          ay = max(1, int(item["size_y"] * item["resize_pct"] / 100))
          self.log_signal.emit(
              f"   Параметры: Кадры {item['start_frame']}-{item['end_frame']}, "
              f"Размер: {ax}x{ay} (база {item['size_x']}x{item['size_y']}, Resize {item['resize_pct']:g}%)"
          )
          if item["output_path"]:
              self.log_signal.emit(f"   Путь вывода: {item['output_path']}")
          self.log_signal.emit(f"   Skip: {'Да' if item['skip_val'] == '1' else 'Нет'}")

          if item["skip_val"] == "1" and item["output_path"]:
              if self.all_frames_exist(
                  item["output_path"],
                  item["start_frame"],
                  item["end_frame"],
                  item["hip_file"],
                  item["rop_name"],
              ):
                  self.log_signal.emit(f"✅ Пропускаю рендер, все кадры уже существуют: {item['output_path']}")
                  completed_time = datetime.now().strftime("%H:%M:%S")
                  self.update_row_signal.emit(row, "Skipped", completed_time, completed_time)
                  continue

          start_time = datetime.now().strftime("%H:%M:%S")
          self.update_row_signal.emit(row, "Running", start_time, "")

          try:
              frame_cb = None
              if item["send2bot"] > 0 and item["output_path"]:
                  frame_cb = lambda f, p, it=item: self.send_frame_preview(f, p, it["rop_name"])

              progress_cb = lambda ratio, r=row: self.frame_progress_signal.emit(r, ratio)

              run_render(
                  scene=item["hip_file"],
                  rop=item["rop_name"],
                  renderer=item["rop_type"],
                  start_frame=item["start_frame"],
                  end_frame=item["end_frame"],
                  size_x=item["size_x"],
                  size_y=item["size_y"],
                  resize_pct=item["resize_pct"],
                  render_width=item["render_width"],
                  render_height=item["render_height"],
                  output_path=item["output_path"],
                  log_callback=self.log_signal.emit,
                  send2bot=item["send2bot"],
                  hip_file=item["hip_file"],
                  frame_callback=frame_cb,
                  progress_callback=progress_cb,
                  skip_existing_frames=item["skip_val"] == "1",
              )

              if self.isInterruptionRequested():
                  self.update_row_signal.emit(row, "Stopped", "", datetime.now().strftime("%H:%M:%S"))
                  break

              self.update_row_signal.emit(row, "Completed", "", datetime.now().strftime("%H:%M:%S"))
          except Exception as e:
              self.log_signal.emit(f"❌ Ошибка при рендеринге {item['rop_name']}: {e}")
              self.update_row_signal.emit(row, "Failed", "", datetime.now().strftime("%H:%M:%S"))
          self.msleep(100)

      self.finished_signal.emit(self.isInterruptionRequested())

  def send_frame_preview(self, frame, frame_path, rop_name=""):
      self.log_signal.emit(f"📤 Отправка кадра {frame} в Telegram: {os.path.basename(frame_path)}")
      try:
          caption = f"Frame {frame}"
          if rop_name:
              caption += f" — {rop_name}"
          caption += f" — {os.path.basename(frame_path)}"
          sent, err = send_image(frame_path, caption=caption)
          if sent:
              self.log_signal.emit(f"✅ Кадр {frame} отправлен в Telegram: {os.path.basename(frame_path)}")
          else:
              detail = f" ({err})" if err else ""
              self.log_signal.emit(
                  f"⚠️ Не удалось отправить кадр {frame}: {os.path.basename(frame_path)}{detail}"
              )
      except Exception as e:
          self.log_signal.emit(f"⚠️ Ошибка при отправке кадра {frame}: {e}")

  def all_frames_exist(self, output_path, start_frame, end_frame, hip_file=None, op_name=None):
      existing_frames = {
          frame for frame, _ in self.resolve_rendered_frames(
              output_path, start_frame, end_frame, hip_file, op_name
          )
      }
      return existing_frames == set(range(start_frame, end_frame + 1))

  def resolve_rendered_frames(self, output_path, start_frame, end_frame, hip_file=None, op_name=None):
      candidates = []
      if not output_path:
          return candidates
      for frame in range(start_frame, end_frame + 1):
          candidate = expand_frame_in_path(output_path, frame, hip_file, op_name)
          if candidate and os.path.exists(candidate):
              candidates.append((frame, candidate))
      if candidates:
          return candidates
      glob_path = resolve_houdini_vars(output_path, hip_file, op_name)
      glob_path = re.sub(r"\$F(\d+)", "*", glob_path)
      glob_path = re.sub(r"\$F\b", "*", glob_path)
      glob_path = re.sub(r"%0(\d+)d", "*", glob_path)
      glob_path = glob_path.replace("#", "*")
      directory = os.path.dirname(glob_path) or "."
      if not os.path.isdir(directory):
          return candidates
      for file_path in sorted(glob.glob(glob_path)):
          frame_match = re.search(r"(\d+)(?=[^\d]*$)", file_path)
          if frame_match:
              frame = int(frame_match.group(1))
              if start_frame <= frame <= end_frame:
                  candidates.append((frame, file_path))
      return candidates

  def is_preview_frame(self, frame_path):
      basename = os.path.basename(frame_path).lower()
      if "aov" in basename:
          return False
      ext = os.path.splitext(frame_path)[1].lower()
      return ext in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".exr"}

class RenderManager(QWidget):
  def _apply_header_logo(self, logo_path):
      if not logo_path or not hasattr(self, "app_logo_label"):
          return
      logo_px = QPixmap(logo_path)
      if logo_px.isNull():
          return
      scaled_logo = logo_px.scaledToHeight(
          HEADER_LOGO_HEIGHT_PX, Qt.TransformationMode.SmoothTransformation
      )
      self.app_logo_label.setPixmap(scaled_logo)
      self.app_logo_label.setFixedSize(scaled_logo.size())

  def __init__(self):
      super().__init__()
      self.current_language = "en"
      self.saved_geometry = None
      self.saved_splitter_state = None
      self.initialized = False  # Prevent save_state() during initialization
      self.last_scanned_hip = None
      self.ui_elements = {}
      self.queue_thread = None
      self._queue_cell_edit_guard = False
      self._resize_update_guard = False
      self._render_job_cur = 0
      self._render_job_total = 0

      self.setWindowTitle(TRANSLATIONS[self.current_language]["title"])
      icon_path = app_icon_path()
      if os.path.exists(icon_path):
          self.setWindowIcon(QIcon(icon_path))
      self.setAcceptDrops(True)
      main_layout = QVBoxLayout(self)

      # --- Zone 1 ---
      group1 = QGroupBox(TRANSLATIONS[self.current_language]["zone1"])
      self.ui_elements["group1"] = group1
      group1.setMaximumHeight(60)  # Fixed height for Zone 1
      zone1 = QHBoxLayout()
      zone1.setContentsMargins(5, 5, 5, 5)
      zone1.addWidget(QLabel(TRANSLATIONS[self.current_language]["houdini_version"]))
      self.houdini_versions = QComboBox()
      self.houdini_versions.addItems(self.detect_houdini_versions())
      self.houdini_versions.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # Make ComboBox expandable
      zone1.addWidget(self.houdini_versions)
      zone1.addStretch()  # Fill space between ComboBox and Browse button

      browse_btn = QPushButton(TRANSLATIONS[self.current_language]["browse"])
      self.ui_elements["browse_btn"] = browse_btn
      browse_btn.clicked.connect(self.browse_hython)
      zone1.addWidget(browse_btn)

      save_btn = QPushButton(TRANSLATIONS[self.current_language]["save_settings"])
      self.ui_elements["save_btn"] = save_btn
      save_btn.clicked.connect(self.save_settings)
      zone1.addWidget(save_btn)

      self.check_btn = QPushButton(TRANSLATIONS[self.current_language]["check_env"])
      self.ui_elements["check_btn"] = self.check_btn
      self.check_btn.clicked.connect(self.check_environment)
      zone1.addWidget(self.check_btn)

      telegram_btn = QPushButton(TRANSLATIONS[self.current_language]["telegram_settings"])
      self.ui_elements["telegram_btn"] = telegram_btn
      telegram_btn.clicked.connect(self.open_telegram_settings)
      zone1.addWidget(telegram_btn)

      self.language_btn = QPushButton(self.current_language.upper())
      self.ui_elements["language_btn"] = self.language_btn
      self.language_btn.clicked.connect(self.switch_language)
      zone1.addWidget(self.language_btn)

      group1.setLayout(zone1)

      self._top_bar = QWidget()
      self._top_bar.setObjectName("appHeader")
      top_layout = QHBoxLayout(self._top_bar)
      top_layout.setContentsMargins(0, 0, 0, 6)
      top_layout.setSpacing(12)
      top_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

      self.app_logo_label = QLabel()
      self.app_logo_label.setScaledContents(False)
      self.app_title_label = QLabel("HOUDINI RENDER MANAGER")
      self.app_title_label.setObjectName("appTitleLabel")
      self._apply_header_logo(find_bundled_file("logo_met2.png"))

      top_layout.addWidget(self.app_logo_label, 0, Qt.AlignmentFlag.AlignVCenter)
      top_layout.addWidget(self.app_title_label, 0, Qt.AlignmentFlag.AlignVCenter)
      top_layout.addWidget(group1, 1)

      # --- Zone 2 & 3 ---
      top_zone_layout = QHBoxLayout()
      
      group2 = QGroupBox(TRANSLATIONS[self.current_language]["zone2"])
      self.ui_elements["group2"] = group2
      zone2 = QVBoxLayout()
      
      zone2.addWidget(QLabel(TRANSLATIONS[self.current_language]["hip_files"]))
      
      self.hip_list = HipList(self)
      self.hip_list.itemSelectionChanged.connect(self.on_hip_selection_changed)
      self.hip_list.currentItemChanged.connect(self.on_hip_current_changed)
      self.hip_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
      self.hip_list.customContextMenuRequested.connect(self.on_hip_context_menu)
      zone2.addWidget(self.hip_list)

      self.hip_scan_label = QLabel()
      self.hip_scan_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
      self.ui_elements["hip_scan_label"] = self.hip_scan_label
      zone2.addWidget(self.hip_scan_label)
      
      hip_btns_layout = QHBoxLayout()
      hip_btns_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
      add_btn = QPushButton(TRANSLATIONS[self.current_language]["add_hip"])
      self.ui_elements["add_btn"] = add_btn
      add_btn.clicked.connect(self.add_hip_files)
      hip_btns_layout.addWidget(add_btn)

      remove_btn = QPushButton(TRANSLATIONS[self.current_language]["remove_hip"])
      self.ui_elements["remove_btn"] = remove_btn
      remove_btn.clicked.connect(self.remove_hip_file)
      hip_btns_layout.addWidget(remove_btn)
      
      zone2.addLayout(hip_btns_layout)
      group2.setLayout(zone2)

      # --- Zone 3 ---
      group3 = QGroupBox(TRANSLATIONS[self.current_language]["zone3"])
      self.ui_elements["group3"] = group3
      group3.setMinimumWidth(200)
      zone3 = QHBoxLayout()
      self.scan_btn = QPushButton(TRANSLATIONS[self.current_language]["scan_hip"])
      self.ui_elements["scan_btn"] = self.scan_btn
      self.scan_btn.clicked.connect(self.scan_hip_file)
      self.scan_btn.setEnabled(False)
      set_disabled_style(self.scan_btn)
      zone3.addWidget(self.scan_btn)
      group3.setLayout(zone3)
      
      # --- Zone 4 ---
      group4 = QGroupBox(TRANSLATIONS[self.current_language]["zone4"])
      self.ui_elements["group4"] = group4
      zone4 = QVBoxLayout()
      self.found_nodes_label = QLabel(TRANSLATIONS[self.current_language]["found_nodes"])
      self.ui_elements["found_nodes_label"] = self.found_nodes_label
      zone4.addWidget(self.found_nodes_label)
      self.rop_count_label = QLabel()
      self.rop_count_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
      self.ui_elements["rop_count_label"] = self.rop_count_label
      zone4.addWidget(self.rop_count_label)
      self.scan_hint_label = QLabel(TRANSLATIONS[self.current_language]["scan_hint"])
      self.scan_hint_label.setStyleSheet("color: #888888; font-size: 11px;")
      self.ui_elements["scan_hint_label"] = self.scan_hint_label
      zone4.addWidget(self.scan_hint_label)
      filter_layout = QHBoxLayout()
      self.filter_redshift = QCheckBox(TRANSLATIONS[self.current_language]["redshift"])
      self.filter_karma = QCheckBox(TRANSLATIONS[self.current_language]["karma"])
      self.filter_other = QCheckBox(TRANSLATIONS[self.current_language]["other"])
      self.ui_elements["filter_redshift"] = self.filter_redshift
      self.ui_elements["filter_karma"] = self.filter_karma
      self.ui_elements["filter_other"] = self.filter_other
      for f in [self.filter_redshift, self.filter_karma, self.filter_other]:
          f.stateChanged.connect(self.apply_filter)
          filter_layout.addWidget(f)
      zone4.addLayout(filter_layout)
      self.rop_list = QListWidget()
      self.rop_list.setSelectionMode(QAbstractItemView.MultiSelection)
      zone4.addWidget(self.rop_list)

      rop_btn_layout = QHBoxLayout()
      self.add_queue_btn = QPushButton(TRANSLATIONS[self.current_language]["add_queue"])
      self.ui_elements["add_queue_btn"] = self.add_queue_btn
      self.add_queue_btn.clicked.connect(self.add_to_queue)
      self.add_queue_btn.setEnabled(False)
      set_disabled_style(self.add_queue_btn)
      rop_btn_layout.addWidget(self.add_queue_btn)

      self.add_all_rops_btn = QPushButton(TRANSLATIONS[self.current_language]["add_all_rops"])
      self.ui_elements["add_all_rops_btn"] = self.add_all_rops_btn
      self.add_all_rops_btn.clicked.connect(self.add_all_visible_rops)
      self.add_all_rops_btn.setEnabled(False)
      set_disabled_style(self.add_all_rops_btn)
      rop_btn_layout.addWidget(self.add_all_rops_btn)
      
      zone4.addLayout(rop_btn_layout)
      group4.setLayout(zone4)
      
      top_zone_layout.addWidget(group2, 1)
      top_zone_layout.addWidget(group3, 0)
      top_zone_layout.addWidget(group4, 1)
      
      # We need a container widget for the top layout to put it in the splitter
      top_container = QWidget()
      top_container.setLayout(top_zone_layout)
      self.ui_elements["top_container"] = top_container

      # --- Zone 5 ---
      group5 = QGroupBox(TRANSLATIONS[self.current_language]["zone5"])
      self.ui_elements["group5"] = group5
      zone5 = QVBoxLayout()
      self.render_progress_label = QLabel()
      self.render_progress_label.setStyleSheet("color: #00BFFF; font-size: 12px;")
      self.ui_elements["render_progress_label"] = self.render_progress_label
      zone5.addWidget(self.render_progress_label)
      self.queue_table = RenderQueueTable(self)
      self.queue_table.setColumnCount(16)
      self.queue_table.setHorizontalHeaderLabels(
          TRANSLATIONS[self.current_language]["queue_headers"]
      )
      self.queue_table.setColumnWidth(12, 100)
      self.queue_table.setColumnWidth(0, 56)
      self.queue_table.setColumnWidth(1, 260)
      self.queue_table.setColumnWidth(2, 180)
      self.queue_table.setColumnWidth(6, 56)
      self.queue_table.setColumnWidth(10, 320)
      self.toggle_delegate = ToggleCheckBoxDelegate(
          self.queue_table, on_toggled=self._on_queue_toggle_changed
      )
      self.queue_table.setItemDelegateForColumn(0, self.toggle_delegate)
      self.queue_table.setItemDelegateForColumn(6, self.toggle_delegate)
      self.path_edit_delegate = FullPathEditDelegate(
          self.queue_table, on_committed=self._on_path_cell_committed
      )
      self.status_progress_delegate = StatusProgressDelegate(self.queue_table)
      self.queue_table.setItemDelegateForColumn(COL_HIP, self.path_edit_delegate)
      self.queue_table.setItemDelegateForColumn(COL_OUTPUT, self.path_edit_delegate)
      self.queue_table.setItemDelegateForColumn(COL_STATUS, self.status_progress_delegate)
      self.queue_table.cellChanged.connect(self.on_queue_cell_changed)
      self.queue_table.cellDoubleClicked.connect(self.on_queue_cell_double_clicked)
      self.queue_table.selectionModel().selectionChanged.connect(self.on_queue_selection_changed)
      self.queue_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
      self.queue_table.customContextMenuRequested.connect(self.on_queue_context_menu)
      zone5.addWidget(self.queue_table)

      btn_layout1 = QHBoxLayout()
      self.start_btn = QPushButton(TRANSLATIONS[self.current_language]["start_render"])
      self.ui_elements["start_btn"] = self.start_btn
      self.start_btn.setEnabled(False)
      set_disabled_style(self.start_btn)
      self.start_btn.clicked.connect(self.start_render)
      btn_layout1.addWidget(self.start_btn)

      self.stop_btn = QPushButton(TRANSLATIONS[self.current_language]["stop_render"])
      self.ui_elements["stop_btn"] = self.stop_btn
      self.stop_btn.setEnabled(False)
      set_disabled_style(self.stop_btn)
      self.stop_btn.clicked.connect(self.stop_render)
      btn_layout1.addWidget(self.stop_btn)
      zone5.addLayout(btn_layout1)

      btn_layout2 = QHBoxLayout()
      self.enable_all_btn = QPushButton(TRANSLATIONS[self.current_language]["enable_all"])
      self.ui_elements["enable_all_btn"] = self.enable_all_btn
      self.enable_all_btn.clicked.connect(lambda: self.set_all_queue_enabled(True))
      btn_layout2.addWidget(self.enable_all_btn)

      self.disable_all_btn = QPushButton(TRANSLATIONS[self.current_language]["disable_all"])
      self.ui_elements["disable_all_btn"] = self.disable_all_btn
      self.disable_all_btn.clicked.connect(lambda: self.set_all_queue_enabled(False))
      btn_layout2.addWidget(self.disable_all_btn)

      self.open_hip_btn = QPushButton(TRANSLATIONS[self.current_language]["open_hip"])
      self.ui_elements["open_hip_btn"] = self.open_hip_btn
      self.open_hip_btn.clicked.connect(self.open_selected_hip)
      btn_layout2.addWidget(self.open_hip_btn)

      self.open_output_btn = QPushButton(TRANSLATIONS[self.current_language]["open_output"])
      self.ui_elements["open_output_btn"] = self.open_output_btn
      self.open_output_btn.clicked.connect(self.open_selected_output_folder)
      btn_layout2.addWidget(self.open_output_btn)

      self.duplicate_btn = QPushButton(TRANSLATIONS[self.current_language]["duplicate"])
      self.ui_elements["duplicate_btn"] = self.duplicate_btn
      self.duplicate_btn.setEnabled(False)
      set_disabled_style(self.duplicate_btn)
      self.duplicate_btn.clicked.connect(self.duplicate_queue_row)
      btn_layout2.addWidget(self.duplicate_btn)

      self.reset_btn = QPushButton(TRANSLATIONS[self.current_language]["reset_rop"])
      self.ui_elements["reset_btn"] = self.reset_btn
      self.reset_btn.setEnabled(False)
      set_disabled_style(self.reset_btn)
      self.reset_btn.clicked.connect(self.reset_rop)
      btn_layout2.addWidget(self.reset_btn)

      self.remove_rop_btn = QPushButton(TRANSLATIONS[self.current_language]["remove_rop"])
      self.ui_elements["remove_rop_btn"] = self.remove_rop_btn
      self.remove_rop_btn.setEnabled(False)
      set_disabled_style(self.remove_rop_btn)
      self.remove_rop_btn.clicked.connect(self.remove_rop_from_queue)
      btn_layout2.addWidget(self.remove_rop_btn)
      zone5.addLayout(btn_layout2)
      group5.setLayout(zone5)

      # --- Log ---
      self.log_output = QTextEdit()
      self.log_output.setReadOnly(True)
      self.log_output.setStyleSheet("QTextEdit { background-color: #191919; color: #ffffff; border: 1px solid #555555; }")
      clear_log_btn = QPushButton(TRANSLATIONS[self.current_language]["clear_log"])
      self.ui_elements["clear_log_btn"] = clear_log_btn
      clear_log_btn.clicked.connect(self.clear_log)

      self.main_splitter = MainSplitter(Qt.Orientation.Vertical)
      self.main_splitter.addWidget(top_container)
      self.main_splitter.addWidget(group5)
      self.main_splitter.addWidget(self.log_output)
      self.main_splitter.configure_handles(
          TRANSLATIONS[self.current_language]["splitter_queue_resize"]
      )
      main_layout.addWidget(self._top_bar)
      main_layout.addWidget(self.main_splitter)
      main_layout.addWidget(clear_log_btn)

      self.all_rops = []
      self._render_jobs = []
      self.load_filters()
      self.restore_window()
      
      # Apply dark theme
      apply_dark_theme(self)
      
      self.main_splitter.setSizes([400, 200, 150])

  def restore_window(self):
      if os.path.exists(CONFIG_FILE):
          try:
              with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                  data = json.load(f)
              if "language" in data:
                  self.current_language = data["language"]
              if "geometry" in data and data["geometry"]:
                  try:
                      geom = QByteArray.fromHex(data["geometry"].encode())
                      self.restoreGeometry(geom)
                  except Exception as e:
                      self.log(f"Ошибка восстановления геометрии: {e}")
              if "splitter_state" in data and data["splitter_state"]:
                  try:
                      state = QByteArray.fromHex(data["splitter_state"].encode())
                      self.main_splitter.restoreState(state)
                  except Exception as e:
                      self.log(f"Ошибка восстановления splitter: {e}")
              if hasattr(self, "main_splitter"):
                  self.main_splitter.configure_handles(
                      TRANSLATIONS[self.current_language]["splitter_queue_resize"]
                  )
              if "hip_files" in data:
                  if data["hip_files"]:
                      for hip in data["hip_files"]:
                          self.hip_list.addItem(hip)
                      if self.hip_list.count() > 0:
                          self.hip_list.setCurrentRow(0)
                      self.on_hip_selection_changed()
                      self.update_hip_current_visual()
              
              # Restore queue
              if "queue" in data:
                  if data["queue"]:
                      for entry in data["queue"]:
                          row = self.queue_table.rowCount()
                          self.queue_table.insertRow(row)
                          self._populate_queue_row(row, entry=entry)
                      self.log(f"Восстановлена очередь из {len(data['queue'])} элементов")
          except Exception as e:
              self.log(f"Ошибка восстановления окна: {e}")
      
      # Ensure window is on screen
      screen = QApplication.primaryScreen().availableGeometry()
      geom = self.geometry()
      if geom.x() < 0 or geom.y() < 0 or geom.x() + geom.width() > screen.width() or geom.y() + geom.height() > screen.height():
          self.move(max(0, min(geom.x(), screen.width() - geom.width())), 
                    max(0, min(geom.y(), screen.height() - geom.height())))

      # Fallback resize if no geometry was restored
      if not self.isMinimized() and not self.isMaximized():
          if self.width() < 100: 
              self.resize(1200, 800)
      
      # Apply translations after restore
      self.language_btn.setText(self.current_language.upper())
      self.apply_translations()
      
      # Restore queue table column widths
      try:
          if os.path.exists(CONFIG_FILE):
              with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                  data = json.load(f)
              if "ui" in data and "column_widths" in data["ui"]:
                  widths = data["ui"]["column_widths"]
                  for i, width in enumerate(widths):
                      if i < self.queue_table.columnCount():
                          self.queue_table.setColumnWidth(i, width)
      except Exception as e:
          self.log(f"Warning: Could not restore column widths: {e}")
      
      # Update Start button based on queue
      self.update_start_button()
      
      # Mark initialization as complete
      self.initialized = True
      self._check_preview_dependencies()

  def _check_preview_dependencies(self):
      from telegram_notifier import check_preview_dependencies

      ok, msg, hint = check_preview_dependencies()
      if ok:
          return
      self.log(f"⚠️ Telegram превью: {msg}")
      if hint:
          self.log(f"   {hint}")

  def open_telegram_settings(self):
      from telegram_notifier import reload_config, DEFAULT_PREVIEW_MAX_SIDE, PREVIEW_MIN_SIDE, PREVIEW_MAX_SIDE_LIMIT

      dlg = QDialog(self)
      dlg.setWindowTitle(TRANSLATIONS[self.current_language]["telegram_settings"])
      layout = QVBoxLayout(dlg)
      token_input = QLineEdit()
      chat_input = QLineEdit()
      preview_max_spin = QSpinBox()
      preview_max_spin.setRange(PREVIEW_MIN_SIDE, PREVIEW_MAX_SIDE_LIMIT)
      preview_max_spin.setSingleStep(100)
      preview_max_spin.setValue(DEFAULT_PREVIEW_MAX_SIDE)

      if os.path.exists(CONFIG_FILE):
          try:
              with open(CONFIG_FILE, encoding="utf-8") as f:
                  cfg = json.load(f)
              tg = cfg.get("telegram", {})
              token_input.setText(tg.get("bot_token", ""))
              chat_input.setText(str(tg.get("chat_id", "")))
              try:
                  preview_max_spin.setValue(int(tg.get("preview_max_side", DEFAULT_PREVIEW_MAX_SIDE)))
              except (TypeError, ValueError):
                  preview_max_spin.setValue(DEFAULT_PREVIEW_MAX_SIDE)
          except json.JSONDecodeError:
              pass

      layout.addWidget(QLabel(TRANSLATIONS[self.current_language]["bot_token"]))
      layout.addWidget(token_input)
      layout.addWidget(QLabel(TRANSLATIONS[self.current_language]["chat_id"]))
      layout.addWidget(chat_input)
      layout.addWidget(QLabel(TRANSLATIONS[self.current_language]["tg_preview_max"]))
      layout.addWidget(preview_max_spin)
      hint = QLabel(TRANSLATIONS[self.current_language]["tg_preview_hint"])
      hint.setWordWrap(True)
      layout.addWidget(hint)

      save_btn = QPushButton(TRANSLATIONS[self.current_language]["save"])
      check_btn = QPushButton(TRANSLATIONS[self.current_language]["check_bot"])
      test_btn = QPushButton(TRANSLATIONS[self.current_language]["send_test"])

      def save_cfg():
          if os.path.exists(CONFIG_FILE):
              with open(CONFIG_FILE, encoding="utf-8") as f:
                  try:
                      data = json.load(f)
                  except json.JSONDecodeError:
                      data = {}
          else:
              data = {}
          data.setdefault("telegram", {})
          data["telegram"]["bot_token"] = token_input.text()
          data["telegram"]["chat_id"] = chat_input.text()
          data["telegram"]["preview_max_side"] = preview_max_spin.value()
          with open(CONFIG_FILE, "w", encoding="utf-8") as f:
              json.dump(data, f, indent=4, ensure_ascii=False)
          reload_config()
          dlg.accept()
          self.log(TRANSLATIONS[self.current_language]["tg_saved"])

      def check_bot():
          token = token_input.text()
          chat_id = chat_input.text()
          if not token or not chat_id:
              self.log("⚠️ Telegram токен или chat_id не заданы.")
              return
          url = f"https://api.telegram.org/bot{token}/getMe"
          try:
              resp = requests.get(url, timeout=5)
              if resp.status_code == 200:
                  self.log("✅ Telegram бот доступен.")
              else:
                  self.log(f"❌ Ошибка подключения: {resp.status_code}")
          except Exception as e:
              self.log(f"Ошибка проверки Telegram: {e}")

      def send_test_message():
          token = token_input.text()
          chat_id = chat_input.text()
          if not token or not chat_id:
              self.log("⚠️ Telegram токен или chat_id не заданы.")
              return
          url = f"https://api.telegram.org/bot{token}/sendMessage"
          payload = {"chat_id": chat_id, "text": "🚀 Test message from Houdini Render Manager!"}
          try:
              resp = requests.post(url, json=payload, timeout=5)
              if resp.status_code == 200:
                  self.log("✅ Тестовое сообщение отправлено!")
              else:
                  self.log(f"❌ Ошибка отправки: {resp.status_code}")
          except Exception as e:
              self.log(f"Ошибка при отправке тестового сообщения: {e}")

      save_btn.clicked.connect(save_cfg)
      check_btn.clicked.connect(check_bot)
      test_btn.clicked.connect(send_test_message)
      layout.addWidget(save_btn)
      layout.addWidget(check_btn)
      layout.addWidget(test_btn)
      dlg.exec()

  def dragEnterEvent(self, event):
      if event.mimeData().hasUrls():
          event.acceptProposedAction()

  def dropEvent(self, event):
      event.acceptProposedAction()
      for url in event.mimeData().urls():
          path = url.toLocalFile()
          if path.lower().endswith(".hip"):
              self.hip_list.addItem(path)
      if self.hip_list.count() > 0 and not self.hip_list.currentItem():
          self.hip_list.setCurrentRow(self.hip_list.count() - 1)
      self.on_hip_selection_changed()
      self.update_hip_current_visual()
      if hasattr(self, "save_state"):
          self.save_state()

  def closeEvent(self, event):
      self.save_state()
      super().closeEvent(event)

  def detect_houdini_versions(self):
      base = r"C:\Program Files\Side Effects Software"
      versions = []
      if os.path.exists(base):
          for entry in os.listdir(base):
              if entry.startswith("Houdini"):
                  hython = os.path.join(base, entry, "bin", "hython.exe")
                  if os.path.exists(hython):
                      versions.append(hython)
      return versions

  def browse_hython(self):
      file, _ = QFileDialog.getOpenFileName(
          self, "Выбрать hython.exe", "", "Executable (*.exe)"
      )
      if file:
          self.houdini_versions.addItem(file)
          self.houdini_versions.setCurrentText(file)
          self.log(f"Выбран hython.exe: {file}")

  def check_environment(self):
      path = self.houdini_versions.currentText()
      if os.path.exists(path):
          self.log(f"✅ Houdini найден: {path}")
      else:
          self.log(f"❌ Houdini не найден: {path}")

      from telegram_notifier import check_preview_dependencies

      ok, msg, hint = check_preview_dependencies()
      if ok:
          self.log("✅ Зависимости Telegram превью (Pillow) установлены")
      else:
          self.log(f"❌ Telegram превью: {msg}")
          if hint:
              self.log(f"   {hint}")

  def switch_language(self):
      if self.current_language == "en":
          self.current_language = "ru"
      else:
          self.current_language = "en"
      self.language_btn.setText(self.current_language.upper())
      self.apply_translations()
      self.save_state()

  def apply_translations(self):
      """Apply translations to all UI elements"""
      t = TRANSLATIONS[self.current_language]
      
      self.setWindowTitle(t["title"])
      self.ui_elements["group1"].setTitle(t["zone1"])
      self.ui_elements["group2"].setTitle(t["zone2"])
      self.ui_elements["group3"].setTitle(t["zone3"])
      self.ui_elements["group4"].setTitle(t["zone4"])
      self.ui_elements["group5"].setTitle(t["zone5"])
      if hasattr(self, "main_splitter"):
          self.main_splitter.configure_handles(t["splitter_queue_resize"])
      self._apply_header_logo(find_bundled_file("logo_met2.png"))

      self.ui_elements["browse_btn"].setText(t["browse"])
      self.ui_elements["save_btn"].setText(t["save_settings"])
      self.ui_elements["check_btn"].setText(t["check_env"])
      self.ui_elements["telegram_btn"].setText(t["telegram_settings"])
      self.ui_elements["add_btn"].setText(t["add_hip"])
      self.ui_elements["remove_btn"].setText(t["remove_hip"])
      self.ui_elements["scan_btn"].setText(t["scan_hip"])
      self.ui_elements["add_queue_btn"].setText(t["add_queue"])
      self.ui_elements["add_all_rops_btn"].setText(t["add_all_rops"])
      self.ui_elements["start_btn"].setText(t["start_render"])
      self.ui_elements["stop_btn"].setText(t["stop_render"])
      self.ui_elements["reset_btn"].setText(t["reset_rop"])
      self.ui_elements["remove_rop_btn"].setText(t["remove_rop"])
      self.ui_elements["clear_log_btn"].setText(t["clear_log"])
      
      self.ui_elements["filter_redshift"].setText(t["redshift"])
      self.ui_elements["filter_karma"].setText(t["karma"])
      self.ui_elements["filter_other"].setText(t["other"])
      
      self.ui_elements["found_nodes_label"].setText(t["found_nodes"])
      self.ui_elements["scan_hint_label"].setText(t["scan_hint"])
      self.ui_elements["enable_all_btn"].setText(t["enable_all"])
      self.ui_elements["disable_all_btn"].setText(t["disable_all"])
      self.ui_elements["open_hip_btn"].setText(t["open_hip"])
      self.ui_elements["open_output_btn"].setText(t["open_output"])
      self.ui_elements["duplicate_btn"].setText(t["duplicate"])
      
      self.queue_table.setHorizontalHeaderLabels(t["queue_headers"])
      self.update_hip_scan_label()
      self.update_rop_count_label()

  def get_active_hip_path(self):
      current = self.hip_list.currentItem()
      if current:
          return current.text()
      selected = self.hip_list.selectedItems()
      if selected:
          return selected[0].text()
      return None

  def update_hip_scan_label(self):
      t = TRANSLATIONS[self.current_language]
      path = self.get_active_hip_path()
      if path:
          self.hip_scan_label.setText(f"{t['scan_for']} {os.path.basename(path)}")
      else:
          self.hip_scan_label.setText(f"{t['scan_for']} {t['scan_for_none']}")

  def update_hip_current_visual(self):
      current = self.hip_list.currentItem()
      for i in range(self.hip_list.count()):
          item = self.hip_list.item(i)
          font = item.font()
          font.setBold(item is current)
          item.setFont(font)

  def on_hip_current_changed(self, current, previous):
      self.update_hip_current_visual()
      self.update_hip_scan_label()

  def _on_queue_toggle_changed(self):
      if self.initialized:
          self.save_state()

  def _make_readonly_item(self, text):
      item = QTableWidgetItem(text)
      item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
      return item

  def _path_display(self, full_path):
      if not full_path:
          return ""
      norm = full_path.replace("\\", "/")
      parts = [p for p in norm.split("/") if p]
      if len(norm) > 52 and len(parts) > 2:
          return "…/" + "/".join(parts[-3:])
      return full_path

  def _make_path_item(self, full_path, editable=False, hip_file=None, op_name=None):
      full_path = (full_path or "").strip()
      item = QTableWidgetItem(self._path_display(full_path))
      item.setData(FULL_PATH_ROLE, full_path)
      tip = path_tooltip(full_path, hip_file, op_name)
      if tip:
          item.setToolTip(tip)
      if not editable:
          item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
      return item

  def _get_cell_path(self, item):
      if item is None:
          return ""
      stored = item.data(FULL_PATH_ROLE)
      if stored:
          return str(stored).strip()
      return item.text().strip()

  def _on_path_cell_committed(self, row, col, path):
      """Called when user finishes editing HIP or Output path in the line editor."""
      hip = self._get_cell_path(self.queue_table.item(row, COL_HIP)) if col == COL_OUTPUT else None
      rop_item = self.queue_table.item(row, COL_ROP)
      op_name = rop_item.text() if rop_item and col == COL_OUTPUT else None
      path = normalize_output_template(path.strip()) if path else ""
      self._set_path_cell(row, col, path, hip_file=hip, op_name=op_name)
      if col == COL_OUTPUT and path:
          self.log(f"Путь вывода рендера: {path}")
      if self.initialized:
          self.save_state()

  def _set_path_cell(self, row, col, path, hip_file=None, op_name=None):
      """Update path cell display without treating it as user edit."""
      item = self.queue_table.item(row, col)
      if not item:
          return
      path = (path or "").strip()
      if col == COL_OUTPUT:
          if hip_file is None:
              hip_item = self.queue_table.item(row, COL_HIP)
              hip_file = self._get_cell_path(hip_item)
          if op_name is None:
              rop_item = self.queue_table.item(row, COL_ROP)
              op_name = rop_item.text() if rop_item else None
          tip = path_tooltip(path, hip_file, op_name)
      else:
          tip = path or ""
      self._queue_cell_edit_guard = True
      self.queue_table.blockSignals(True)
      try:
          item.setData(FULL_PATH_ROLE, path)
          if tip:
              item.setToolTip(tip)
          item.setText(self._path_display(path))
      finally:
          self.queue_table.blockSignals(False)
          self._queue_cell_edit_guard = False

  def _queue_has_rop(self, hip_path, rop_name):
      for row in range(self.queue_table.rowCount()):
          hip_item = self.queue_table.item(row, COL_HIP)
          rop_item = self.queue_table.item(row, COL_ROP)
          if not hip_item or not rop_item:
              continue
          if (
              norm_path_key(self._get_cell_path(hip_item)) == norm_path_key(hip_path)
              and rop_item.text() == rop_name
          ):
              return True
      return False

  def set_all_queue_enabled(self, enabled):
      for row in range(self.queue_table.rowCount()):
          item = self.queue_table.item(row, 0)
          if item:
              apply_toggle_cell_style(item, enabled)
      if self.initialized:
          self.save_state()

  def _get_selected_queue_row(self):
      indexes = self.queue_table.selectedIndexes()
      return indexes[0].row() if indexes else None

  def open_selected_hip(self):
      row = self._get_selected_queue_row()
      if row is None:
          self.log("⚠️ Выберите строку в очереди.")
          return
      path = self._get_cell_path(self.queue_table.item(row, COL_HIP))
      if path and os.path.isfile(path):
          os.startfile(path)
      else:
          self.log(f"⚠️ HIP не найден: {path}")

  def open_selected_output_folder(self):
      row = self._get_selected_queue_row()
      if row is None:
          self.log("⚠️ Выберите строку в очереди.")
          return
      path = self._get_cell_path(self.queue_table.item(row, COL_OUTPUT))
      hip = self._get_cell_path(self.queue_table.item(row, COL_HIP))
      if not path:
          self.log(TRANSLATIONS[self.current_language]["path_empty"])
          return
      rop = self.queue_table.item(row, COL_ROP)
      op_name = rop.text() if rop else None
      probe = resolve_houdini_vars(path, hip, op_name)
      probe = re.sub(r"\$F\d*", "0001", probe)
      probe = re.sub(r"\$F\b", "1", probe)
      folder = probe if os.path.isdir(probe) else os.path.dirname(probe)
      if folder and os.path.isdir(folder):
          os.startfile(folder)
      else:
          self.log(f"⚠️ Папка не найдена: {folder}")

  def _read_base_resolution(self, row):
      """Read base (unscaled) resolution from UserRole only."""
      sx = self.queue_table.item(row, 7)
      sy = self.queue_table.item(row, 8)
      base_x = base_y = None
      if sx:
          raw = sx.data(BASE_SIZE_X_ROLE)
          if raw is not None and str(raw).strip() != "":
              base_x = max(1, int(float(raw)))
      if sy:
          raw = sy.data(BASE_SIZE_Y_ROLE)
          if raw is not None and str(raw).strip() != "":
              base_y = max(1, int(float(raw)))
      return base_x, base_y

  def _sanitize_saved_base(self, entry, base_x, base_y):
      """Fix configs where size_x_base accidentally stored the scaled size."""
      resize_pct = self._parse_resize_pct(entry.get("resize", "100"))
      if abs(resize_pct - 100.0) < 0.001:
          return base_x, base_y
      try:
          display_x = int(float(entry.get("size_x", base_x)))
          display_y = int(float(entry.get("size_y", base_y)))
      except (TypeError, ValueError):
          return base_x, base_y
      expected_x = max(1, int(base_x * resize_pct / 100))
      expected_y = max(1, int(base_y * resize_pct / 100))
      if abs(display_x - expected_x) <= max(2, int(expected_x * 0.05)) and abs(
          display_y - expected_y
      ) <= max(2, int(expected_y * 0.05)):
          return base_x, base_y
      recovered_x = max(1, int(round(display_x * 100.0 / resize_pct)))
      recovered_y = max(1, int(round(display_y * 100.0 / resize_pct)))
      if recovered_x > base_x * 1.2 or recovered_y > base_y * 1.2:
          return recovered_x, recovered_y
      return base_x, base_y

  def _legacy_base_from_entry(self, entry):
      """One-time recovery of base size from old configs without size_x_base."""
      resize_pct = self._parse_resize_pct(entry.get("resize", "100"))
      try:
          sx = int(float(entry.get("size_x", 1920) or 1920))
          sy = int(float(entry.get("size_y", 1080) or 1080))
      except (TypeError, ValueError):
          return 1920, 1080
      if abs(resize_pct - 100.0) > 0.001:
          return (
              max(1, int(round(sx * 100.0 / resize_pct))),
              max(1, int(round(sy * 100.0 / resize_pct))),
          )
      return max(1, sx), max(1, sy)

  def _restore_resolution_columns(self, row, entry):
      """Restore resize/size columns without writing scaled values into base role."""
      try:
          resize_pct = self._parse_resize_pct(entry.get("resize", "100"))
          resize_text = str(entry.get("resize", "100")).strip()
          if resize_text and not resize_text.endswith("%"):
              resize_text = f"{resize_pct:g}%"

          if entry.get("size_x_base") not in (None, ""):
              base_x = max(1, int(float(entry["size_x_base"])))
              base_y = max(1, int(float(entry.get("size_y_base", entry.get("size_y", 1080)))))
              base_x, base_y = self._sanitize_saved_base(entry, base_x, base_y)
          else:
              base_x, base_y = self._legacy_base_from_entry(entry)

          self._resize_update_guard = True
          self.queue_table.blockSignals(True)
          try:
              self.queue_table.setItem(row, 9, QTableWidgetItem(resize_text))
              self.queue_table.setItem(row, 7, QTableWidgetItem(""))
              self.queue_table.setItem(row, 8, QTableWidgetItem(""))
              self._set_base_resolution(row, base_x, base_y)
          finally:
              self.queue_table.blockSignals(False)
              self._resize_update_guard = False

          self._apply_resize_display(row, base_x=base_x, base_y=base_y)
      except (TypeError, ValueError):
          pass

  def _set_base_resolution(self, row, base_x, base_y):
      sx = self.queue_table.item(row, 7)
      sy = self.queue_table.item(row, 8)
      if sx:
          sx.setData(BASE_SIZE_X_ROLE, str(int(base_x)))
      if sy:
          sy.setData(BASE_SIZE_Y_ROLE, str(int(base_y)))

  def _parse_resize_pct(self, resize_text):
      if not resize_text:
          return 100.0
      text = str(resize_text).strip().rstrip("%")
      try:
          return float(text) if text else 100.0
      except ValueError:
          return 100.0

  def _resolve_render_size(self, row, base_x=None, base_y=None):
      """Base from UserRole + Resize % -> final resolution. Never derive base from display text."""
      rz = self.queue_table.item(row, 9)
      resize_pct = self._parse_resize_pct(rz.text() if rz else "100")
      if base_x is None or base_y is None:
          role_x, role_y = self._read_base_resolution(row)
          base_x = base_x if base_x is not None else (role_x or 1920)
          base_y = base_y if base_y is not None else (role_y or 1080)
      self._set_base_resolution(row, base_x, base_y)
      actual_x = max(1, int(base_x * resize_pct / 100))
      actual_y = max(1, int(base_y * resize_pct / 100))
      return base_x, base_y, resize_pct, actual_x, actual_y

  def _apply_resize_display(self, row, base_x=None, base_y=None):
      """Update Size X/Y display cells; base resolution stays in UserRole."""
      base_x, base_y, resize_pct, actual_x, actual_y = self._resolve_render_size(
          row, base_x=base_x, base_y=base_y
      )
      sx = self.queue_table.item(row, 7)
      sy = self.queue_table.item(row, 8)
      self._resize_update_guard = True
      self.queue_table.blockSignals(True)
      try:
          if sx:
              sx.setText(str(actual_x))
          if sy:
              sy.setText(str(actual_y))
      finally:
          self.queue_table.blockSignals(False)
          self._resize_update_guard = False
      return base_x, base_y, resize_pct, actual_x, actual_y

  def _update_render_progress(self, cur, total, row, status):
      t = TRANSLATIONS[self.current_language]
      if not status or total <= 0:
          self.render_progress_label.setText(t["render_progress_idle"])
          self.setWindowTitle(t["title"])
          return
      hip_item = self.queue_table.item(row, COL_HIP)
      rop_item = self.queue_table.item(row, COL_ROP)
      hip = os.path.basename(self._get_cell_path(hip_item)) if hip_item else "?"
      rop = rop_item.text() if rop_item else "?"
      self.render_progress_label.setText(
          t["render_progress"].format(cur=cur, total=total, hip=hip, rop=rop, status=status)
      )
      self.setWindowTitle(f"{t['title']} — {status} ({cur}/{total})")

  def update_rop_count_label(self):
      t = TRANSLATIONS[self.current_language]
      total = len(self.all_rops)
      shown = self.rop_list.count()
      self.rop_count_label.setText(t["rop_count"].format(shown=shown, total=total))

  def _populate_queue_row(self, row, entry=None, rop_name=None, rop_type=None, rop_data=None, hip_path=None):
      """Fill one queue table row from a saved entry or new ROP data."""
      if entry is not None:
          for col, key in enumerate(QUEUE_COLUMN_KEYS):
              raw_val = entry.get(key, "")
              if col in (0, 6):
                  checked = normalize_toggle_value(raw_val, "1" if col == 0 else "0") == "1"
                  if col == 0 and (raw_val is None or raw_val == ""):
                      checked = True
                  self.queue_table.setItem(row, col, create_toggle_item(checked))
              elif col == COL_HIP:
                  hip_val = str(raw_val or "")
                  self.queue_table.setItem(
                      row, col, self._make_path_item(hip_val, editable=False, hip_file=hip_val)
                  )
              elif col == COL_OUTPUT:
                  hip_val = str(entry.get("hip", "") or "")
                  rop_val = str(entry.get("rop", "") or "")
                  self.queue_table.setItem(
                      row, col,
                      self._make_path_item(
                          str(raw_val or ""), editable=True, hip_file=hip_val, op_name=rop_val
                      ),
                  )
              elif col in (7, 8, 9):
                  continue
              else:
                  text = "" if raw_val is None else str(raw_val)
                  item = QTableWidgetItem(text)
                  if col not in (4, 5, 10, 12):
                      item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                  self.queue_table.setItem(row, col, item)
                  if col == COL_STATUS:
                      apply_status_style(item, text)
          self._restore_resolution_columns(row, entry)
          return

      enabled_default = True
      skip_default = bool(rop_data.get("skip_existing")) if rop_data else False
      self.queue_table.setItem(row, 0, create_toggle_item(enabled_default))
      self.queue_table.setItem(row, 6, create_toggle_item(skip_default))

      if not hip_path:
          if rop_data and rop_data.get("hip"):
              hip_path = rop_data.get("hip")
          elif self.last_scanned_hip:
              hip_path = self.last_scanned_hip
          else:
              hip_path = self.get_active_hip_path() or ""
      self.queue_table.setItem(row, COL_HIP, self._make_path_item(hip_path, editable=False, hip_file=hip_path))
      self.queue_table.setItem(row, COL_ROP, self._make_readonly_item(rop_name or ""))
      self.queue_table.setItem(row, 3, self._make_readonly_item(rop_type or ""))

      start_frame = str(rop_data.get("start_frame", "1")) if rop_data else "1"
      end_frame = str(rop_data.get("end_frame", "100")) if rop_data else "100"
      self.queue_table.setItem(row, 4, QTableWidgetItem(start_frame))
      self.queue_table.setItem(row, 5, QTableWidgetItem(end_frame))

      size_x = str(rop_data.get("size_x", "1920")) if rop_data else "1920"
      size_y = str(rop_data.get("size_y", "1080")) if rop_data else "1080"
      resize_val = str(entry.get("resize", "100")) if entry else "100"
      if not resize_val.endswith("%"):
          resize_val = f"{resize_val}%"
      self.queue_table.setItem(row, 7, QTableWidgetItem(size_x))
      self.queue_table.setItem(row, 8, QTableWidgetItem(size_y))
      self.queue_table.setItem(row, 9, QTableWidgetItem(resize_val))
      self._set_base_resolution(row, size_x, size_y)
      self._apply_resize_display(row)

      output_path = (rop_data.get("output_path", "") if rop_data else "").strip()
      self.queue_table.setItem(
          row, COL_OUTPUT,
          self._make_path_item(output_path, editable=True, hip_file=hip_path, op_name=rop_name or ""),
      )
      status_item = self._make_readonly_item("Queued")
      apply_status_style(status_item, "Queued")
      self.queue_table.setItem(row, COL_STATUS, status_item)
      self.queue_table.setItem(row, 12, QTableWidgetItem("0"))
      self.queue_table.setItem(row, 13, self._make_readonly_item(""))
      self.queue_table.setItem(row, 14, self._make_readonly_item(""))
      self.queue_table.setItem(row, 15, self._make_readonly_item("--"))

  def save_settings(self):
      self.save_state()
      self.log("Настройки сохранены.")

  def on_hip_selection_changed(self):
      if self.hip_list.selectedItems():
          self.scan_btn.setEnabled(True)
          set_next_style(self.scan_btn)
          self.ui_elements["remove_btn"].setEnabled(True)
          self.ui_elements["remove_btn"].setStyleSheet("QPushButton:enabled { background-color: #d32f2f; color: #fff; }")
          if not self.hip_list.currentItem():
              self.hip_list.setCurrentItem(self.hip_list.selectedItems()[0])
      else:
          self.scan_btn.setEnabled(False)
          set_disabled_style(self.scan_btn)
          self.ui_elements["remove_btn"].setEnabled(False)
          set_disabled_style(self.ui_elements["remove_btn"])
      self.update_hip_scan_label()

  def add_hip_files(self):
      files, _ = QFileDialog.getOpenFileNames(
          self, "Выбрать HIP файлы", "", "HIP Files (*.hip)"
      )
      for f in files:
          self.hip_list.addItem(f)
      if self.hip_list.count() > 0 and not self.hip_list.currentItem():
          self.hip_list.setCurrentRow(self.hip_list.count() - 1)
      self.on_hip_selection_changed()
      self.update_hip_current_visual()
      self.save_state()

  def remove_hip_file(self):
      for item in self.hip_list.selectedItems():
          self.hip_list.takeItem(self.hip_list.row(item))
      self.save_state()
      self.on_hip_selection_changed()
      if self.hip_list.count() == 0:
          self.scan_btn.setEnabled(False)
          set_disabled_style(self.scan_btn)
          self.add_queue_btn.setEnabled(False)
          set_disabled_style(self.add_queue_btn)
          self.add_all_rops_btn.setEnabled(False)
          set_disabled_style(self.add_all_rops_btn)

  def on_queue_context_menu(self, pos):
      row = self.queue_table.rowAt(pos.y())
      if row < 0:
          return
      self.queue_table.selectRow(row)
      t = TRANSLATIONS[self.current_language]
      menu = QMenu(self)
      menu.addAction(t["ctx_reset_status"], lambda: self._context_reset_status(row))
      menu.addSeparator()
      menu.addAction(t["ctx_enable"], lambda: self._context_set_enabled(row, True))
      menu.addAction(t["ctx_disable"], lambda: self._context_set_enabled(row, False))
      menu.addAction(t["ctx_duplicate"], lambda: self.duplicate_queue_row(row))
      menu.addSeparator()
      menu.addAction(t["ctx_reset"], self.reset_rop)
      menu.addAction(t["ctx_remove"], self.remove_rop_from_queue)
      menu.addSeparator()
      menu.addAction(t["ctx_open_hip"], self.open_selected_hip)
      menu.addAction(t["ctx_open_output"], self.open_selected_output_folder)
      menu.exec(self.queue_table.viewport().mapToGlobal(pos))

  def _context_reset_status(self, row):
      if self.queue_thread and self.queue_thread.isRunning():
          active = any(j.get("row") == row for j in getattr(self, "_render_jobs", []))
          if active:
              self.log("⚠️ Нельзя сбросить статус строки, которая сейчас рендерится.")
              return
      status_item = self._make_readonly_item("Queued")
      apply_status_style(status_item, "Queued")
      self.queue_table.setItem(row, COL_STATUS, status_item)
      self._set_status_render_progress(row, None)
      for col in (13, 14):
          item = self.queue_table.item(row, col)
          if item:
              item.setText("")
      duration_item = self.queue_table.item(row, 15)
      if duration_item:
          duration_item.setText("--")
      if self.initialized:
          self.save_state()
      rop_item = self.queue_table.item(row, COL_ROP)
      rop_name = rop_item.text() if rop_item else "?"
      self.log(f"✓ Статус сброшен на Queued: {rop_name}")

  def _context_set_enabled(self, row, enabled):
      item = self.queue_table.item(row, 0)
      if item:
          apply_toggle_cell_style(item, enabled)
          if self.initialized:
              self.save_state()

  def on_hip_context_menu(self, pos):
      item = self.hip_list.itemAt(pos)
      if not item:
          return
      self.hip_list.setCurrentItem(item)
      menu = QMenu(self)
      menu.addAction(TRANSLATIONS[self.current_language]["scan_hip"], self.scan_hip_file)
      menu.addAction(TRANSLATIONS[self.current_language]["remove_hip"], self.remove_hip_file)
      menu.exec(self.hip_list.viewport().mapToGlobal(pos))

  def apply_filter(self):
      self.update_rop_list()
      self.save_state()

  def update_start_button(self):
      """Update Start button state based on queue and worker state"""
      if self.queue_thread and self.queue_thread.isRunning():
          self.start_btn.setEnabled(False)
          set_disabled_style(self.start_btn)
          return
      if self.queue_table.rowCount() > 0:
          self.start_btn.setEnabled(True)
          set_next_style(self.start_btn)
      else:
          self.start_btn.setEnabled(False)
          set_disabled_style(self.start_btn)

  def add_all_visible_rops(self):
      if self.rop_list.count() == 0:
          return
      for i in range(self.rop_list.count()):
          self.rop_list.item(i).setSelected(True)
      self.add_to_queue()

  def add_to_queue(self):
      selected_rops = self.rop_list.selectedItems()
      if not selected_rops:
          self.log("⚠️ Не выбраны ROP для добавления в очередь.")
          return

      added = 0
      hip_path = self.last_scanned_hip or self.get_active_hip_path() or ""
      t = TRANSLATIONS[self.current_language]
      for rop_item in selected_rops:
          rop_text = rop_item.text()
          rop_name, rop_type = rop_text.split(":", 1)
          if hip_path and self._queue_has_rop(hip_path, rop_name):
              self.log(t["duplicate_rop"].format(rop=rop_name, hip=os.path.basename(hip_path)))
              continue
          rop_data = next((r for r in self.all_rops if r["name"] == rop_name), None)
          row = self.queue_table.rowCount()
          self.queue_table.insertRow(row)
          self._populate_queue_row(
              row, rop_name=rop_name, rop_type=rop_type, rop_data=rop_data, hip_path=hip_path
          )
          out_item = self.queue_table.item(row, COL_OUTPUT)
          if out_item and not self._get_cell_path(out_item):
              self.log(
                  f"⚠️ {rop_name}: {TRANSLATIONS[self.current_language]['path_empty']}"
              )
          added += 1

      self.log(f"Добавлено {added} ROP(ов) в очередь.")
      self.update_start_button()
      self.save_state()

  def clear_log(self):
      self.log_output.clear()
      self.log("Лог очищен.")

  def save_state(self):
      # Prevent saving during initialization
      if not self.initialized:
          return
      
      try:
          # Read existing config to preserve other settings (like telegram)
          data = {}
          if os.path.exists(CONFIG_FILE):
              try:
                  with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                      data = json.load(f)
              except (json.JSONDecodeError, IOError):
                  data = {}

          # Save Houdini path
          data["hython_path"] = self.houdini_versions.currentText()

          # Save HIP files
          data["hip_files"] = [self.hip_list.item(i).text() for i in range(self.hip_list.count())]
          
          # Save queue
          data["queue"] = [
              self._queue_row_to_entry(row)
              for row in range(self.queue_table.rowCount())
          ]

          # Save language
          data["language"] = self.current_language
          
          # Save window geometry
          try:
              geometry_hex = self.saveGeometry().toHex().data().decode()
              if geometry_hex:
                  data["geometry"] = geometry_hex
                  
                  # Also save explicit width/height and position for fallback or manual check
                  if "ui" not in data:
                      data["ui"] = {}
                  data["ui"]["width"] = self.width()
                  data["ui"]["height"] = self.height()
                  data["ui"]["x"] = self.x()
                  data["ui"]["y"] = self.y()
                  
                  splitter_hex = self.main_splitter.saveState().toHex().data().decode()
                  if splitter_hex:
                      data["splitter_state"] = splitter_hex
          except Exception as e:
              self.log(f"Warning: Could not save geometry/splitter: {e}")
          
          # Save queue table column widths
          try:
              if "ui" not in data:
                  data["ui"] = {}
              data["ui"]["column_widths"] = [self.queue_table.columnWidth(i) for i in range(self.queue_table.columnCount())]
          except Exception as e:
              self.log(f"Warning: Could not save column widths: {e}")

          # Write config with explicit encoding
          with open(CONFIG_FILE, "w", encoding="utf-8") as f:
              json.dump(data, f, indent=4, ensure_ascii=False)
      except Exception as e:
          self.log(f"Error saving state: {e}")

  def start_render(self):
      if self.queue_table.rowCount() == 0:
          self.log("⚠️ Очередь рендера пуста.")
          return
      if self.queue_thread and self.queue_thread.isRunning():
          self.log("⚠️ Очередь уже выполняется.")
          return

      self.log("▶️ Начинается рендер очереди...")
      self.stop_btn.setEnabled(True)
      set_delete_style(self.stop_btn)
      self.start_btn.setEnabled(False)
      set_disabled_style(self.start_btn)

      queue_data = []
      for row in range(self.queue_table.rowCount()):
          enabled_item = self.queue_table.item(row, 0)
          hip_item = self.queue_table.item(row, 1)
          rop_item = self.queue_table.item(row, 2)
          type_item = self.queue_table.item(row, 3)
          start_item = self.queue_table.item(row, 4)
          end_item = self.queue_table.item(row, 5)
          skip_item = self.queue_table.item(row, 6)
          size_x_item = self.queue_table.item(row, 7)
          size_y_item = self.queue_table.item(row, 8)
          resize_item = self.queue_table.item(row, 9)
          output_item = self.queue_table.item(row, 10)
          send2bot_item = self.queue_table.item(row, 12)

          enabled_val = enabled_item.data(Qt.UserRole) if enabled_item and enabled_item.data(Qt.UserRole) is not None else "1"
          if enabled_val == "0":
              self.log(f"⏭️ Строка {row+1}: отключена, пропускаю.")
              continue

          hip_file = self._get_cell_path(hip_item)
          rop_name = rop_item.text() if rop_item else ""
          rop_type = type_item.text() if type_item else ""
          start_frame_str = start_item.text() if start_item else "1"
          end_frame_str = end_item.text() if end_item else "100"
          skip_val = skip_item.data(Qt.UserRole) if skip_item and skip_item.data(Qt.UserRole) is not None else "0"

          size_x_str = size_x_item.text() if size_x_item else "1920"
          size_y_str = size_y_item.text() if size_y_item else "1080"
          resize_str = resize_item.text() if resize_item else "100"
          output_path = self._get_cell_path(output_item)
          try:
              send2bot = int(send2bot_item.text()) if send2bot_item and send2bot_item.text() else 0
              if send2bot < 0:
                  send2bot = 0
          except ValueError:
              send2bot = 0

          if not hip_file or not rop_name:
              self.log(f"⚠️ Строка {row+1}: HIP файл или ROP не указаны. Пропускаю.")
              continue

          if not output_path:
              self.log(
                  f"⚠️ Строка {row+1} ({rop_name}): "
                  f"{TRANSLATIONS[self.current_language]['path_empty']}"
              )

          try:
              start_frame = int(start_frame_str) if start_frame_str else 1
              end_frame = int(end_frame_str) if end_frame_str else 100
          except ValueError:
              self.log(f"⚠️ Строка {row+1}: Неверный диапазон кадров. Используются значения по умолчанию (1-100).")
              start_frame = 1
              end_frame = 100

          base_x, base_y, resize_pct, actual_x, actual_y = self._resolve_render_size(row)

          queue_data.append({
              "row": row,
              "hip_file": hip_file,
              "rop_name": rop_name,
              "rop_type": rop_type,
              "start_frame": start_frame,
              "end_frame": end_frame,
              "skip_val": skip_val,
              "size_x": base_x,
              "size_y": base_y,
              "resize_pct": resize_pct,
              "render_width": actual_x,
              "render_height": actual_y,
              "output_path": output_path,
              "send2bot": send2bot,
          })

      if not queue_data:
          self.log("⚠️ Нет включённых задач для рендера.")
          self.stop_btn.setEnabled(False)
          set_disabled_style(self.stop_btn)
          self.update_start_button()
          return

      self._render_jobs = queue_data
      self.queue_thread = RenderQueueWorker(queue_data)
      self.queue_thread.log_signal.connect(self.log)
      self.queue_thread.update_row_signal.connect(self.on_worker_update_row)
      self.queue_thread.progress_signal.connect(self.on_render_progress)
      self.queue_thread.frame_progress_signal.connect(self.on_render_frame_progress)
      self.queue_thread.finished_signal.connect(self.on_queue_finished)
      self.queue_thread.start()

  def _format_running_status(self, ratio=None):
      parts = []
      if ratio is not None:
          try:
              parts.append(f"{int(float(ratio) * 100)}%")
          except (TypeError, ValueError):
              pass
      if self._render_job_total > 0:
          parts.append(f"{self._render_job_cur}/{self._render_job_total}")
      if not parts:
          return "Running"
      return "Running " + " · ".join(parts)

  def _set_status_render_progress(self, row, ratio=None):
      status_item = self.queue_table.item(row, COL_STATUS)
      if not status_item:
          return
      if ratio is None:
          status_item.setData(RENDER_PROGRESS_ROLE, None)
      else:
          status_item.setData(RENDER_PROGRESS_ROLE, float(ratio))
          status_item.setText(self._format_running_status(ratio))
          apply_status_style(status_item, "Running")
      self.queue_table.update(self.queue_table.model().index(row, COL_STATUS))

  def _clear_all_status_render_progress(self):
      for row in range(self.queue_table.rowCount()):
          item = self.queue_table.item(row, COL_STATUS)
          if item and item.data(RENDER_PROGRESS_ROLE) is not None:
              item.setData(RENDER_PROGRESS_ROLE, None)
              self.queue_table.update(self.queue_table.model().index(row, COL_STATUS))

  def on_render_frame_progress(self, row, ratio):
      self._set_status_render_progress(row, ratio)

  def on_render_progress(self, cur, total, row):
      self._render_job_cur = cur
      self._render_job_total = total
      self._clear_all_status_render_progress()
      self._set_status_render_progress(row, 0.0)
      self._update_render_progress(cur, total, row, "Running")
      self.queue_table.selectRow(row)
      item = self.queue_table.item(row, 0)
      if item:
          self.queue_table.scrollToItem(item)

  def stop_render(self):
      t = TRANSLATIONS[self.current_language]
      if self.queue_thread and self.queue_thread.isRunning():
          reply = QMessageBox.question(
              self,
              t["confirm_stop_title"],
              t["confirm_stop_text"],
              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
              QMessageBox.StandardButton.No,
          )
          if reply != QMessageBox.StandardButton.Yes:
              return
      self.log("⏹️ Попытка остановить рендер...")
      if self.queue_thread and self.queue_thread.isRunning():
          self.queue_thread.requestInterruption()
      if stop_render():
          self.log("✅ Процесс рендера остановлен.")
          for row in range(self.queue_table.rowCount()):
              status_item = self.queue_table.item(row, COL_STATUS)
              if status_item and status_item.text() == "Running":
                  status_item.setText("Stopped")
                  apply_status_style(status_item, "Stopped")
          self._clear_all_status_render_progress()
          self._render_job_cur = 0
          self._render_job_total = 0
          self._update_render_progress(0, 0, 0, "")
          self.save_state()
      else:
          self.log("⚠️ Процесс рендера не запущен или не удалось его остановить.")

      self.stop_btn.setEnabled(False)
      set_disabled_style(self.stop_btn)
      self.update_start_button()

  def on_worker_update_row(self, row, status, start_time, end_time):
      if status == "Running":
          self._set_status_render_progress(row, 0.0)
      else:
          self._set_status_render_progress(row, None)
          status_item = self.queue_table.item(row, COL_STATUS)
          if status_item:
              status_item.setText(status)
              apply_status_style(status_item, status)
      start_time_item = self.queue_table.item(row, 13)
      end_time_item = self.queue_table.item(row, 14)
      duration_item = self.queue_table.item(row, 15)
      if start_time and start_time_item:
          start_time_item.setText(start_time)
      if end_time and end_time_item:
          end_time_item.setText(end_time)
      if duration_item and start_time_item and end_time_item:
          duration_item.setText(
              format_duration_hms(start_time_item.text(), end_time_item.text())
          )

  def on_queue_finished(self, cancelled):
      if cancelled:
          self.log("\n⏹️ Очередь рендера остановлена пользователем.")
      else:
          self.log("\n✅ Очередь рендера завершена.")
      self.queue_thread = None
      self._render_jobs = []
      self._clear_all_status_render_progress()
      self._render_job_cur = 0
      self._render_job_total = 0
      self._update_render_progress(0, 0, 0, "")
      self.stop_btn.setEnabled(False)
      set_disabled_style(self.stop_btn)
      self.update_start_button()
      self.save_state()

  def _queue_row_to_entry(self, row):
      """Serialize one queue row for save/duplicate."""
      entry = {}
      for col, key in enumerate(QUEUE_COLUMN_KEYS):
          cell = self.queue_table.item(row, col)
          if col in (0, 6):
              default = "1" if col == 0 else "0"
              raw = cell.data(Qt.UserRole) if cell else None
              entry[key] = normalize_toggle_value(raw, default)
          elif key in ("hip", "output_path"):
              entry[key] = self._get_cell_path(cell)
          elif col in (7, 8, 9):
              continue
          else:
              entry[key] = cell.text() if cell else ""
      base_x, base_y = self._read_base_resolution(row)
      if base_x is None or base_y is None:
          base_x, base_y, _, actual_x, actual_y = self._resolve_render_size(row)
      else:
          rz_item = self.queue_table.item(row, 9)
          resize_pct = self._parse_resize_pct(rz_item.text() if rz_item else "100")
          actual_x = max(1, int(base_x * resize_pct / 100))
          actual_y = max(1, int(base_y * resize_pct / 100))
      entry["size_x_base"] = str(base_x)
      entry["size_y_base"] = str(base_y)
      entry["size_x"] = str(actual_x)
      entry["size_y"] = str(actual_y)
      rz_item = self.queue_table.item(row, 9)
      entry["resize"] = rz_item.text() if rz_item else "100%"
      return entry

  def duplicate_queue_row(self, row=None):
      if row is None:
          selected = self.queue_table.selectedIndexes()
          if not selected:
              self.log("⚠️ Выберите элемент в очереди.")
              return
          row = selected[0].row()
      entry = self._queue_row_to_entry(row)
      entry["status"] = "Queued"
      entry["start_time"] = ""
      entry["end_time"] = ""
      entry["duration"] = "--"
      new_row = row + 1
      self.queue_table.insertRow(new_row)
      self._populate_queue_row(new_row, entry=entry)
      self.queue_table.selectRow(new_row)
      self.update_start_button()
      self.on_queue_selection_changed()
      if self.initialized:
          self.save_state()
      rop_name = entry.get("rop", "?")
      self.log(f"✓ Дубликат добавлен (строка {new_row + 1}): {rop_name}")

  def reset_rop(self):
      selected_rows = self.queue_table.selectedIndexes()
      if not selected_rows:
          self.log("⚠️ Выберите элемент в очереди.")
          return
      row = selected_rows[0].row()
      
      # Get ROP name from column 2
      rop_name_item = self.queue_table.item(row, 2)
      if not rop_name_item:
          return
      
      rop_name = rop_name_item.text()
      
      # Get HIP file from column 1
      hip_item = self.queue_table.item(row, COL_HIP)
      hip_file = self._get_cell_path(hip_item)
      
      if not hip_file:
          self.log("⚠️ HIP файл не указан для этого ROP.")
          return

      self.log(f"🔄 Считывание параметров {rop_name} из {os.path.basename(hip_file)}...")
      
      # Run scan to get latest data
      rops_data, error = self._run_scan(hip_file)
      if error:
          self.log(f"❌ Ошибка при считывании: {error}")
          return
      
      rop_data = next((r for r in rops_data if r["name"] == rop_name), None)
      
      if rop_data:
          # Reset start and end frames from file (columns 4-5)
          start_frame = str(rop_data.get("start_frame", "1"))
          end_frame = str(rop_data.get("end_frame", "100"))
          
          self.queue_table.setItem(row, 4, QTableWidgetItem(start_frame))
          self.queue_table.setItem(row, 5, QTableWidgetItem(end_frame))
          
          skip_checked = bool(rop_data.get("skip_existing"))
          self.queue_table.setItem(row, 6, create_toggle_item(skip_checked))
          
          # Reset Size X and Y (columns 7-8)
          size_x = str(rop_data.get("size_x", "1920"))
          size_y = str(rop_data.get("size_y", "1080"))
          self.queue_table.setItem(row, 7, QTableWidgetItem(size_x))
          self.queue_table.setItem(row, 8, QTableWidgetItem(size_y))
          self.queue_table.setItem(row, 9, QTableWidgetItem("100"))
          self._set_base_resolution(row, size_x, size_y)
          self._apply_resize_display(row)
          
          # Reset Output path (column 10)
          output_path = rop_data.get("output_path", "")
          hip_for_row = self._get_cell_path(self.queue_table.item(row, COL_HIP))
          self.queue_table.setItem(
              row, COL_OUTPUT,
              self._make_path_item(
                  output_path, editable=True, hip_file=hip_for_row, op_name=rop_name
              ),
          )
          
          status_item = self._make_readonly_item("Queued")
          apply_status_style(status_item, "Queued")
          self.queue_table.setItem(row, COL_STATUS, status_item)
          
          self.save_state()
          self.log(f"✓ ROP сброшен на значения из файла: {start_frame}-{end_frame}, размер: {size_x}x{size_y}")
      else:
          self.log(f"⚠️ ROP {rop_name} не найден в файле {os.path.basename(hip_file)}.")

  def remove_rop_from_queue(self):
      selected_rows = self.queue_table.selectedIndexes()
      if not selected_rows:
          self.log("⚠️ Выберите элемент в очереди.")
          return
      row = selected_rows[0].row()
      self.queue_table.removeRow(row)
      self.update_start_button()
      self.save_state()
      self.log("✓ ROP удален из очереди.")

  def on_queue_cell_changed(self, row, col):
      """Handle changes to queue table cells"""
      if self._queue_cell_edit_guard or self._resize_update_guard:
          return

      if col in (COL_HIP, COL_OUTPUT):
          return

      # Block signals to prevent infinite recursion when programmatically updating cells
      self.queue_table.blockSignals(True)
      try:
          # Handle Resize column (col 9) - recalculate Size X/Y
          if col == 9:
              try:
                  base_x, base_y, resize_pct, actual_x, actual_y = self._apply_resize_display(row)
                  self.log(
                      f"Масштабирование {row + 1}: {base_x}x{base_y} -> {actual_x}x{actual_y} ({resize_pct:g}%)"
                  )
              except Exception as e:
                  self.log(f"Ошибка обработки Resize: {e}")

          if col in (7, 8):
              item = self.queue_table.item(row, col)
              if item:
                  try:
                      val = int(float(item.text() or 0))
                      if val > 0:
                          role_x, role_y = self._read_base_resolution(row)
                          base_x = val if col == 7 else (role_x or val)
                          base_y = val if col == 8 else (role_y or val)
                          rz = self.queue_table.item(row, 9)
                          if rz:
                              rz.setText("100%")
                          self._apply_resize_display(row, base_x=base_x, base_y=base_y)
                          self.log(
                              f"Строка {row + 1}: новый базовый размер {base_x}x{base_y}, Resize сброшен на 100%"
                          )
                  except ValueError:
                      pass
          
          # Handle Send2Bot every column (col 12) - normalize integer
          if col == 12:
              item = self.queue_table.item(row, col)
              if item:
                  try:
                      value = int(item.text()) if item.text() else 0
                  except ValueError:
                      value = 0
                  if value < 0:
                      value = 0
                  item.setText(str(value))
      finally:
          # Re-enable signals after all updates
          self.queue_table.blockSignals(False)
      
      # Save state when cells change (except for toggle columns 0 and 6)
      if col not in [0, 6]:
          self.save_state()

  def on_queue_cell_double_clicked(self, row, col):
      if col not in (COL_OUTPUT, COL_HIP):
          return
      item = self.queue_table.item(row, col)
      if not item:
          return
      full = self._get_cell_path(item) or item.text().strip()
      if not full:
          return
      self._queue_cell_edit_guard = True
      self.queue_table.blockSignals(True)
      try:
          item.setText(full)
      finally:
          self.queue_table.blockSignals(False)
          self._queue_cell_edit_guard = False
      self.queue_table.editItem(item)

  def on_queue_selection_changed(self):
      """Handle selection changes in queue table"""
      selected_indexes = self.queue_table.selectedIndexes()
      if selected_indexes:
          self.reset_btn.setEnabled(True)
          set_reset_style(self.reset_btn)
          self.duplicate_btn.setEnabled(True)
          set_next_style(self.duplicate_btn)
          self.remove_rop_btn.setEnabled(True)
          set_delete_style(self.remove_rop_btn)
      else:
          self.reset_btn.setEnabled(False)
          set_disabled_style(self.reset_btn)
          self.duplicate_btn.setEnabled(False)
          set_disabled_style(self.duplicate_btn)
          self.remove_rop_btn.setEnabled(False)
          set_disabled_style(self.remove_rop_btn)

  def log(self, msg):
      self.log_output.append(msg)

  def _run_scan(self, hip_file):
      """Internal method to run scan and return ROP data list"""
      hython_path = self.houdini_versions.currentText()
      if not os.path.exists(hython_path):
          return None, f"Hython not found: {hython_path}"
      try:
          scan_script = hython_script_path("scan_rops.py")
          run_kw = {"capture_output": True, "text": True, "timeout": 30}
          if os.name == "nt":
              run_kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
          result = subprocess.run(
              [hython_path, scan_script, hip_file],
              **run_kw
          )
          if result.returncode == 0:
              stdout_content = result.stdout.strip()
              if stdout_content:
                  start_idx = stdout_content.find('[')
                  end_idx = stdout_content.rfind(']')
                  if start_idx != -1 and end_idx != -1:
                      actual_start = -1
                      for i in range(len(stdout_content)):
                          if stdout_content[i] == '[':
                              if i + 1 < len(stdout_content) and (stdout_content[i+1] == '{' or stdout_content[i+1] == ']'):
                                  actual_start = i
                                  break
                      if actual_start != -1:
                          actual_end = -1
                          for i in range(len(stdout_content) - 1, actual_start, -1):
                              if stdout_content[i] == ']':
                                  if i > 0 and (stdout_content[i-1] == '}' or stdout_content[i-1] == '['):
                                      actual_end = i
                                      break
                          if actual_end != -1:
                              json_str = stdout_content[actual_start:actual_end+1]
                              return json.loads(json_str), None
                      else:
                          return None, "No valid JSON array start found"
                  else:
                      return [], None
              else:
                  return [], None
          else:
              return None, f"Error scanning HIP file: {result.stderr}"
      except Exception as e:
          return None, str(e)
      return None, "Unknown error"

  def scan_hip_file(self):
      hip_file = self.get_active_hip_path()
      if not hip_file:
          self.log("⚠️ No HIP file selected.")
          return

      self.last_scanned_hip = hip_file
      self.update_hip_scan_label()
      
      try:
          rops_data, error = self._run_scan(hip_file)
          if error:
              self.log(f"❌ {error}")
              return
          
          self.all_rops = rops_data
          
          self.log(f"✅ Found {len(self.all_rops)} ROPs in {os.path.basename(hip_file)}")
          self.update_rop_list()
          self.update_rop_count_label()
          self.add_queue_btn.setEnabled(True)
          set_next_style(self.add_queue_btn)
          self.add_all_rops_btn.setEnabled(True)
          set_next_style(self.add_all_rops_btn)
      except Exception as e:
          self.log(f"❌ Error scanning HIP file: {e}")

  def update_rop_list(self):
      self.rop_list.clear()
      for rop in self.all_rops:
          rop_type = rop.get("type", "Unknown")
          
          # Apply filters - show if any filter is checked and matches
          show = False
          any_filter_checked = (self.filter_redshift.isChecked() or 
                               self.filter_karma.isChecked() or 
                               self.filter_other.isChecked())
          
          if not any_filter_checked:
              # If no filters checked, show all
              show = True
          else:
              if self.filter_redshift.isChecked() and "redshift" in rop_type.lower():
                  show = True
              elif self.filter_karma.isChecked() and "karma" in rop_type.lower():
                  show = True
              elif self.filter_other.isChecked() and "redshift" not in rop_type.lower() and "karma" not in rop_type.lower():
                  show = True
          
          if show:
              item_text = f"{rop.get('name', 'Unknown')}:{rop_type}"
              self.rop_list.addItem(item_text)

      self.update_rop_count_label()

  def load_filters(self):
      self.filter_redshift.setChecked(True)

def main():
  import sys
  app = QApplication(sys.argv)
  
  # Load language from config
  language = "en"
  if os.path.exists(CONFIG_FILE):
      try:
          with open(CONFIG_FILE) as f:
              data = json.load(f)
              language = data.get("language", "en")
      except json.JSONDecodeError:
          pass

  # Create window with dark theme
  window = RenderManager()
  window.current_language = language
  apply_dark_theme(app)
  
  # Restore window state and translations
  window.restore_window()
  window.show()
  
  sys.exit(app.exec())

if __name__ == "__main__":
  main()