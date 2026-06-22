import os, json, re, subprocess, requests, sys, time
from datetime import datetime, timedelta
from render_runner import run_render, stop_render
from telegram_notifier import send_image, send_video, get_mp4_max_side, test_bot_connection, send_message, reload_config
from app_paths import config_path, app_icon_path, find_bundled_file, hython_script_path
from queue_model import (
    RenderQueueModel,
    RenderQueueView,
    QUEUE_COLUMN_KEYS,
    COL_HIP,
    COL_ROP,
    COL_OUTPUT,
    COL_STATUS,
    COL_START_TIME,
    COL_END_TIME,
    COL_DURATION,
    COL_ETA,
    COL_SEND2BOT,
    COL_SEND_MP4,
    FULL_PATH_ROLE,
    RENDER_PROGRESS_ROLE,
    BASE_SIZE_X_ROLE,
    BASE_SIZE_Y_ROLE,
    normalize_toggle_value,
    is_toggle_checked_value,
    _empty_row,
)
from ui_theme import apply_dark_theme, TOGGLE_ON_COLOR, TOGGLE_OFF_COLOR
from path_utils import (
    norm_path_key,
    resolve_houdini_vars,
    expand_frame_in_path,
    normalize_output_template,
    path_tooltip,
    missing_render_frames,
)
from i18n import log_msg
from PySide6.QtWidgets import (
      QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QComboBox,
      QFileDialog, QLabel, QDialog, QLineEdit, QTableWidget, QTableWidgetItem,
      QTextEdit, QCheckBox, QGroupBox, QApplication, QAbstractItemView, QSplitter,
      QSplitterHandle, QHeaderView, QScrollArea,
      QSizePolicy, QStyledItemDelegate, QStyle, QStyleOptionButton, QStyleOptionViewItem,
      QMessageBox, QMenu, QLineEdit, QSpinBox, QProgressBar
  )
from PySide6.QtGui import QPalette, QColor, QIcon, QFont, QPainter, QPen, QPixmap
from PySide6.QtCore import Qt, QByteArray, QMimeData, QThread, Signal, QEvent, QRect, QSize, QTimer

CONFIG_FILE = config_path()
HEADER_LOGO_HEIGHT_PX = 27
ZONE3_FIXED_WIDTH = 200


def _horizontal_button_bar(layout, height=34):
    """Button row that scrolls horizontally instead of blocking window resize."""
    bar = QWidget()
    bar.setLayout(layout)
    scroll = QScrollArea()
    scroll.setWidget(bar)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setFixedHeight(height)
    scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return scroll


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
        "queue_headers": ["Enabled","HIP","ROP","Type","Start","End","Skip","Size X","Size Y","Resize","Output","Status","Jpg-TG","MP4-TG","Start Time","End Time","Duration","Estimated finish"],
        "eta_finish_tip": "Remaining: {remaining}\nEstimated finish: {finish} (local)",
        "bot_token": "Bot Token:",
        "chat_id": "Chat ID:",
        "save": "Save",
        "check_bot": "Check Bot",
        "send_test": "Send Test Message",
        "tg_saved": "Telegram settings saved.",
        "tg_preview_max": "Preview max side (px):",
        "tg_preview_hint": "Frame previews: JPEG, longest side limited above. Formats: PNG, JPG, TIF, EXR.",
        "tg_dialog_title": "Telegram notifications",
        "tg_mp4_on_complete": "Default Send MP4 for new queue rows (can change per row in queue)",
        "tg_mp4_max_side": "MP4 max side (px, 0 = use image preview size):",
        "tg_mp4_use_preview": "MP4 uses same max side as image previews",
        "tg_instructions_html": (
            "<p><b style='color:#7ec8e8'>1. Create a bot</b></p>"
            "<ol style='margin-top:4px;margin-bottom:8px;padding-left:22px'>"
            "<li>Open Telegram and message <b>@BotFather</b>.</li>"
            "<li>Send <code>/newbot</code>, choose a name and username (must end with <code>bot</code>).</li>"
            "<li>Copy the <b>HTTP API token</b> — paste it below.</li>"
            "</ol>"
            "<p><b style='color:#7ec8e8'>2. Get your chat ID</b></p>"
            "<ol style='margin-top:4px;margin-bottom:4px;padding-left:22px'>"
            "<li>Open your bot in Telegram and tap <b>Start</b>.</li>"
            "<li>Message <b>@GetId</b> and tap <b>Start</b> — copy the numeric <b>Chat ID</b>.</li>"
            "<li>Paste that ID below (groups often use negative IDs).</li>"
            "</ol>"
            "<p style='color:#a0a8b0;margin-top:8px'>Group: add <b>@GetId</b> to the group. "
            "Alternative: open <code>getUpdates</code> in a browser after messaging your bot.</p>"
        ),
        "workflow_html": (
            "<b style='color:#7ec8e8'>Workflow</b> &nbsp;"
            "① Set <b>hython</b> path &nbsp;→&nbsp; "
            "② Add <b>HIP</b> files &nbsp;→&nbsp; "
            "③ <b>Scan</b> selected HIP &nbsp;→&nbsp; "
            "④ Pick <b>ROPs</b> → Add to queue &nbsp;→&nbsp; "
            "⑤ <b>Start Render</b> &nbsp;|&nbsp; "
            "Drag rows or <b>Up/Down</b> to reorder &nbsp;|&nbsp; "
            "Telegram: frame previews (Send2Bot) + optional MP4 on finish"
        ),
        "zone2_tip": "Add .hip files (drag-and-drop supported). Select one file, then scan.",
        "zone3_tip": "Scan the selected HIP for render nodes (ROPs).",
        "zone4_tip": "Filter ROPs, multi-select, add to the render queue below.",
        "zone5_tip": "Render queue — edit frames, paths, resize. Status shows job progress.",
        "render_progress_idle": "Render progress: idle",
        "render_progress": "Job {cur}/{total}: {hip} → {rop} — {status} ({pct}%)",
        "enable_all": "Enable all",
        "disable_all": "Disable all",
        "open_hip": "Open HIP",
        "open_output": "Open output folder",
        "duplicate": "Duplicate",
        "move_up": "Move up",
        "move_down": "Move down",
        "queue_reorder_blocked": "Cannot reorder queue while rendering.",
        "duplicate_rop": "Already in queue: {rop} ({hip})",
        "rop_count": "Shown: {shown} / {total}",
        "add_all_rops": "Add all visible",
        "confirm_stop_title": "Stop render?",
        "confirm_stop_text": "Stop the current render and remaining queue?",
        "ctx_reset_status": "Reset status",
        "ctx_enable": "Enable",
        "ctx_disable": "Disable",
        "ctx_duplicate": "Duplicate",
        "ctx_move_up": "Move up",
        "ctx_move_down": "Move down",
        "ctx_reset": "Reset from HIP",
        "ctx_remove": "Remove from queue",
        "ctx_open_hip": "Open HIP",
        "ctx_open_output": "Open output folder",
        "path_empty": "Output path is empty — set it in the queue or rescan the ROP.",
        "splitter_queue_resize": "Drag to resize the render queue height (zone 5)",
        "splitter_zones_resize": "Drag to resize HIP list (zone 2) and ROP list (zone 4)",
        "log_position_bottom": "Log: bottom",
        "log_position_right": "Log: right",
        "log_position_tip": "Toggle log panel position (bottom or right side)",
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
        "queue_headers": ["Вкл.","HIP","ROP","Тип","Начало","Конец","Пропуск","Размер X","Размер Y","Масштаб","Путь вывода","Статус","Jpg-TG","MP4-TG","Время начала","Время окончания","Длительность","Окончание ~"],
        "tg_mp4_on_complete": "MP4 для новых строк очереди по умолчанию (в очереди можно изменить)",
        "eta_finish_tip": "Осталось: {remaining}\nПримерное окончание: {finish} (локальное)",
        "bot_token": "Токен бота:",
        "chat_id": "ID чата:",
        "save": "Сохранить",
        "check_bot": "Проверить бота",
        "send_test": "Отправить тестовое сообщение",
        "tg_saved": "Настройки Telegram сохранены.",
        "tg_preview_max": "Макс. сторона превью (px):",
        "tg_preview_hint": "Кадры конвертируются в JPEG с уменьшением (длинная сторона). Форматы: PNG, JPG, TIF, EXR.",
        "tg_dialog_title": "Уведомления Telegram",
        "tg_mp4_max_side": "MP4 макс. сторона (px, 0 = как у картинок):",
        "tg_mp4_use_preview": "MP4 — тот же лимит, что и для JPEG превью",
        "tg_instructions_html": (
            "<p><b style='color:#7ec8e8'>1. Создайте бота</b></p>"
            "<ol style='margin-top:4px;margin-bottom:8px;padding-left:22px'>"
            "<li>В Telegram напишите <b>@BotFather</b>.</li>"
            "<li>Команда <code>/newbot</code>, имя и username (оканчивается на <code>bot</code>).</li>"
            "<li>Скопируйте <b>HTTP API token</b> — вставьте ниже.</li>"
            "</ol>"
            "<p><b style='color:#7ec8e8'>2. Узнайте chat ID</b></p>"
            "<ol style='margin-top:4px;margin-bottom:4px;padding-left:22px'>"
            "<li>Откройте бота и нажмите <b>Start</b>.</li>"
            "<li>Напишите <b>@GetId</b> → <b>Start</b> — скопируйте <b>Chat ID</b>.</li>"
            "<li>Вставьте ID ниже (для групп ID часто отрицательный).</li>"
            "</ol>"
            "<p style='color:#a0a8b0;margin-top:8px'>Группа: добавьте <b>@GetId</b> в чат. "
            "Или <code>getUpdates</code> в браузере после сообщения боту.</p>"
        ),
        "workflow_html": (
            "<b style='color:#7ec8e8'>Порядок работы</b> &nbsp;"
            "① Путь к <b>hython</b> &nbsp;→&nbsp; "
            "② <b>HIP</b> файлы &nbsp;→&nbsp; "
            "③ <b>Скан</b> HIP &nbsp;→&nbsp; "
            "④ <b>ROP</b> → в очередь &nbsp;→&nbsp; "
            "⑤ <b>Старт рендера</b> &nbsp;|&nbsp; "
            "Перетаскивание или <b>Выше/Ниже</b> &nbsp;|&nbsp; "
            "Telegram: кадры (Send2Bot) + MP4 по завершении"
        ),
        "zone2_tip": "Добавьте .hip (можно перетащить). Выберите файл для скана.",
        "zone3_tip": "Скан выбранного HIP на ROP узлы.",
        "zone4_tip": "Фильтр ROP, выбор, добавление в очередь.",
        "zone5_tip": "Очередь рендера — кадры, пути, resize. Статус — прогресс.",
        "render_progress_idle": "Прогресс рендера: ожидание",
        "render_progress": "Задача {cur}/{total}: {hip} → {rop} — {status} ({pct}%)",
        "enable_all": "Включить все",
        "disable_all": "Выключить все",
        "open_hip": "Открыть HIP",
        "open_output": "Папка вывода",
        "duplicate": "Дублировать",
        "move_up": "Выше",
        "move_down": "Ниже",
        "queue_reorder_blocked": "Нельзя менять порядок очереди во время рендера.",
        "duplicate_rop": "Уже в очереди: {rop} ({hip})",
        "rop_count": "Показано: {shown} / {total}",
        "add_all_rops": "Добавить все видимые",
        "confirm_stop_title": "Остановить рендер?",
        "confirm_stop_text": "Остановить текущий рендер и оставшиеся задачи в очереди?",
        "ctx_reset_status": "Сбросить статус",
        "ctx_enable": "Включить",
        "ctx_disable": "Выключить",
        "ctx_duplicate": "Дублировать",
        "ctx_move_up": "Выше",
        "ctx_move_down": "Ниже",
        "ctx_reset": "Сбросить из HIP",
        "ctx_remove": "Удалить из очереди",
        "ctx_open_hip": "Открыть HIP",
        "ctx_open_output": "Папка вывода",
        "path_empty": "Путь вывода пуст — укажите в очереди или пересканируйте ROP.",
        "splitter_queue_resize": "Потяните разделитель, чтобы изменить высоту очереди рендера (зона 5)",
        "splitter_zones_resize": "Потяните разделитель, чтобы изменить ширину зон 2 (HIP) и 4 (ROP)",
        "log_position_bottom": "Лог: снизу",
        "log_position_right": "Лог: справа",
        "log_position_tip": "Переключить положение панели лога (снизу или справа)",
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
            return QSize(0, h)
        if self._style == self.STYLE_QUEUE:
            w = self.QUEUE_HEIGHT
        elif self._style == self.STYLE_FLAT:
            w = self.FLAT_HEIGHT
        else:
            w = self.NORMAL_HEIGHT
        return QSize(w, 0)

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
    """Splitter with optional queue resize grips on selected handle indexes."""

    def __init__(self, orientation, parent=None, queue_handle_indexes=(0, 1)):
        super().__init__(orientation, parent)
        self._queue_handle_indexes = tuple(queue_handle_indexes)

    def createHandle(self):
        return GripSplitterHandle(self.orientation(), self)

    def configure_handles(self, queue_tooltip=""):
        for idx in range(self.count()):
            handle = self.handle(idx)
            if handle is None or not isinstance(handle, GripSplitterHandle):
                continue
            if idx in self._queue_handle_indexes:
                handle.set_style(GripSplitterHandle.STYLE_QUEUE)
                handle.setEnabled(True)
                if queue_tooltip:
                    handle.setToolTip(queue_tooltip)
            else:
                handle.set_style(GripSplitterHandle.STYLE_NORMAL)
                if queue_tooltip:
                    handle.setToolTip(queue_tooltip)


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


def format_eta_finish_cell(seconds):
    """Compact estimated finish clock for the Estimated finish column."""
    if seconds is None or seconds <= 0:
        return "--"
    dt = datetime.now() + timedelta(seconds=int(round(seconds)))
    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    if dt.year == now.year:
        return dt.strftime("%d.%m %H:%M")
    return dt.strftime("%d.%m.%y %H:%M")


def format_remaining_seconds(seconds):
    if seconds is None or seconds <= 0:
        return "--"
    total = int(round(seconds))
    if total < 60:
        return f"~{total}s"
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h >= 24:
        d, h = divmod(h, 24)
        return f"~{d}d {h}:{m:02d}:{s:02d}"
    if h:
        return f"~{h}:{m:02d}:{s:02d}"
    return f"~{m}:{s:02d}"


def finish_clock_from_now(seconds):
    if seconds is None or seconds <= 0:
        return ""
    return (datetime.now() + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")


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
        full = index.data(FULL_PATH_ROLE)
        display = index.data(Qt.ItemDataRole.DisplayRole)
        editor.setText(str(full).strip() if full else (display or ""))

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

        rect = opt.rect
        bg = index.data(Qt.ItemDataRole.BackgroundRole)
        if bg:
            painter.fillRect(rect, bg)
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
        bg = index.data(Qt.ItemDataRole.BackgroundRole)
        if bg:
            painter.fillRect(option.rect, bg)
        style = option.widget.style() if option.widget else QApplication.style()
        checkbox_opt = QStyleOptionButton()
        checkbox_opt.state = QStyle.StateFlag.State_Enabled
        if is_toggle_checked_value(index.data(Qt.ItemDataRole.UserRole)):
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
            checked = is_toggle_checked_value(index.data(Qt.ItemDataRole.UserRole))
            model.setData(index, "0" if checked else "1", Qt.ItemDataRole.UserRole)
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


class CompactListWidget(QListWidget):
    """List that scrolls instead of forcing window height from item count."""

    def minimumSizeHint(self):
        h = max(24, self.fontMetrics().height() * 2 + 4)
        return QSize(0, h)


class HipList(CompactListWidget):
  def __init__(self, parent=None):
      super().__init__(parent)
      self.setAcceptDrops(True)
      self.setMinimumSize(0, 0)
      self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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

class RenderQueueWorker(QThread):
  log_signal = Signal(str)
  update_row_signal = Signal(int, str, str, str)
  progress_signal = Signal(int, int, int)
  frame_progress_signal = Signal(int, float, int, int, float)
  finished_signal = Signal(bool)

  def __init__(self, queue_data, language="en", parent=None):
      super().__init__(parent)
      self.queue_data = queue_data
      self.language = language

  def _log(self, key, **kwargs):
      self.log_signal.emit(log_msg(self.language, key, **kwargs))

  def run(self):
      from datetime import datetime
      cancelled = False
      try:
          total = len(self.queue_data)
          self._log("worker_thread_start", total=total)
          for job_index, item in enumerate(self.queue_data, start=1):
              if self.isInterruptionRequested():
                  cancelled = True
                  break

              row = item["row"]
              self.progress_signal.emit(job_index, total, row)
              self._log(
                  "worker_job",
                  job_index=job_index,
                  total=total,
                  hip=os.path.basename(item["hip_file"]),
                  rop_name=item["rop_name"],
              )
              ax = max(1, int(item["render_width"]))
              ay = max(1, int(item["render_height"]))
              self._log(
                  "worker_params",
                  start_frame=item["start_frame"],
                  end_frame=item["end_frame"],
                  ax=ax,
                  ay=ay,
                  size_x=item["size_x"],
                  size_y=item["size_y"],
                  resize_pct=item["resize_pct"],
              )
              if item["output_path"]:
                  self._log("worker_output_path", path=item["output_path"])
              skip_key = "worker_skip_yes" if item["skip_val"] == "1" else "worker_skip_no"
              self._log(skip_key)

              if item["skip_val"] == "1" and item["output_path"]:
                  total_frames = item["end_frame"] - item["start_frame"] + 1
                  missing = missing_render_frames(
                      item["output_path"],
                      item["start_frame"],
                      item["end_frame"],
                      item["hip_file"],
                      item["rop_name"],
                  )
                  if not missing:
                      self._log(
                          "worker_skip_all",
                          total_frames=total_frames,
                          start_frame=item["start_frame"],
                          end_frame=item["end_frame"],
                      )
                      completed_time = datetime.now().strftime("%H:%M:%S")
                      self.update_row_signal.emit(row, "Skipped", completed_time, completed_time)
                      continue
                  on_disk = total_frames - len(missing)
                  if on_disk > 0:
                      self._log(
                          "worker_skip_partial",
                          on_disk=on_disk,
                          total_frames=total_frames,
                          missing_count=len(missing),
                      )

              start_time = datetime.now().strftime("%H:%M:%S")
              self.update_row_signal.emit(row, "Running", start_time, "")

              try:
                  frame_cb = None
                  if item["send2bot"] > 0 and item["output_path"]:
                      frame_cb = lambda f, p, it=item: self.send_frame_preview(f, p, it["rop_name"])

                  progress_cb = (
                      lambda ratio, wd, wt, fs, r=row: self.frame_progress_signal.emit(
                          r, ratio, wd, wt, fs
                      )
                  )

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
                      language=self.language,
                  )

                  if self.isInterruptionRequested():
                      self.update_row_signal.emit(row, "Stopped", "", datetime.now().strftime("%H:%M:%S"))
                      cancelled = True
                      break

                  self.update_row_signal.emit(row, "Completed", "", datetime.now().strftime("%H:%M:%S"))
                  self.send_mp4_preview(item)
              except Exception as e:
                  self._log("worker_render_error", rop_name=item["rop_name"], e=e)
                  self.update_row_signal.emit(row, "Failed", "", datetime.now().strftime("%H:%M:%S"))
              self.msleep(100)
      except Exception as e:
          self._log("worker_critical", e=e)
          cancelled = self.isInterruptionRequested()
      finally:
          self.finished_signal.emit(cancelled or self.isInterruptionRequested())

  def send_frame_preview(self, frame, frame_path, rop_name=""):
      basename = os.path.basename(frame_path)
      self._log("worker_tg_send_frame", frame=frame, basename=basename)
      try:
          caption = f"Frame {frame}"
          if rop_name:
              caption += f" — {rop_name}"
          caption += f" — {basename}"
          sent, err = send_image(frame_path, caption=caption)
          if sent:
              self._log("worker_tg_frame_ok", frame=frame, basename=basename)
          else:
              detail = f" ({err})" if err else ""
              self._log(
                  "worker_tg_frame_fail",
                  frame=frame,
                  basename=basename,
                  detail=detail,
              )
      except Exception as e:
          self._log("worker_tg_frame_error", frame=frame, e=e)

  def send_mp4_preview(self, item):
      from video_preview import build_mp4_from_sequence
      import telegram_notifier as tg

      mp4_path = None
      tg.reload_config()
      if not item.get("send_mp4"):
          return
      if not item.get("output_path"):
          return
      self._log("worker_mp4_build")
      max_side = get_mp4_max_side()
      mp4_path, err = build_mp4_from_sequence(
          item["output_path"],
          item["start_frame"],
          item["end_frame"],
          hip_file=item["hip_file"],
          op_name=item["rop_name"],
          max_side=max_side,
      )
      if not mp4_path:
          fail_msg = err or ("failed to create" if self.language == "en" else "не удалось создать")
          self._log("worker_mp4_fail_create", err=fail_msg)
          return
      try:
          caption = (
              f"Preview — {item['rop_name']} "
              f"({item['start_frame']}-{item['end_frame']})"
          )
          sent, send_err = send_video(mp4_path, caption=caption)
          if sent:
              self._log("worker_mp4_ok")
          else:
              fail_msg = send_err or ("send error" if self.language == "en" else "ошибка отправки")
              self._log("worker_mp4_send_fail", err=fail_msg)
      except Exception as e:
          self._log("worker_mp4_error", e=e)
      finally:
          try:
              if mp4_path and os.path.isfile(mp4_path):
                  os.remove(mp4_path)
          except OSError:
              pass

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
      self._jobs_done = 0
      self._active_render_ratio = 0.0
      self._progress_ui_row = -1
      self._active_render_rows = []
      self._row_render_start = {}
      self._job_duration_samples = []
      self._row_eta_meta = {}
      self._row_work_ratio = {}
      self._row_work_done = {}
      self._row_last_frame_mono = {}
      self._row_frame_seconds = {}
      self._job_duration_samples = []

      self.setWindowTitle(TRANSLATIONS[self.current_language]["title"])
      icon_path = app_icon_path()
      if os.path.exists(icon_path):
          self.setWindowIcon(QIcon(icon_path))
      self.setAcceptDrops(True)
      self.setMinimumSize(320, 120)
      main_layout = QVBoxLayout(self)

      # --- Zone 1 ---
      group1 = QGroupBox(TRANSLATIONS[self.current_language]["zone1"])
      self.ui_elements["group1"] = group1
      group1.setMaximumHeight(70)  # Zone 1: hython + action buttons
      zone1 = QHBoxLayout()
      zone1.setContentsMargins(5, 5, 5, 5)
      self.houdini_version_label = QLabel(TRANSLATIONS[self.current_language]["houdini_version"])
      self.ui_elements["houdini_version_label"] = self.houdini_version_label
      zone1.addWidget(self.houdini_version_label)
      self.houdini_versions = QComboBox()
      self.houdini_versions.addItems(self.detect_houdini_versions())
      self.houdini_versions.setMinimumContentsLength(0)
      self.houdini_versions.setMinimumWidth(48)
      self.houdini_versions.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
      self.houdini_versions.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
      zone1.addWidget(self.houdini_versions, 1)

      zone1_btns = QHBoxLayout()
      zone1_btns.setContentsMargins(0, 0, 0, 0)
      zone1_btns.setSpacing(4)

      browse_btn = QPushButton(TRANSLATIONS[self.current_language]["browse"])
      self.ui_elements["browse_btn"] = browse_btn
      browse_btn.clicked.connect(self.browse_hython)
      zone1_btns.addWidget(browse_btn)

      save_btn = QPushButton(TRANSLATIONS[self.current_language]["save_settings"])
      self.ui_elements["save_btn"] = save_btn
      save_btn.clicked.connect(self.save_settings)
      zone1_btns.addWidget(save_btn)

      self.check_btn = QPushButton(TRANSLATIONS[self.current_language]["check_env"])
      self.ui_elements["check_btn"] = self.check_btn
      self.check_btn.clicked.connect(self.check_environment)
      zone1_btns.addWidget(self.check_btn)

      telegram_btn = QPushButton(TRANSLATIONS[self.current_language]["telegram_settings"])
      self.ui_elements["telegram_btn"] = telegram_btn
      telegram_btn.clicked.connect(self.open_telegram_settings)
      zone1_btns.addWidget(telegram_btn)

      self.language_btn = QPushButton(self.current_language.upper())
      self.ui_elements["language_btn"] = self.language_btn
      self.language_btn.clicked.connect(self.switch_language)
      zone1_btns.addWidget(self.language_btn)

      self._zone1_btns_widget = QWidget()
      self._zone1_btns_widget.setLayout(zone1_btns)
      self._zone1_btns_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
      zone1.addWidget(self._zone1_btns_widget, 0)

      group1.setLayout(zone1)
      group1.setMinimumWidth(0)
      group1.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

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
      self.app_title_label.setMinimumWidth(0)
      self.app_title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
      self._apply_header_logo(find_bundled_file("logo_met2.png"))

      top_layout.addWidget(self.app_logo_label, 0, Qt.AlignmentFlag.AlignVCenter)
      top_layout.addWidget(self.app_title_label, 0, Qt.AlignmentFlag.AlignVCenter)
      top_layout.addWidget(group1, 1)
      self._top_bar.setMinimumSize(0, 0)

      # --- Zone 2 & 3 & 4 ---
      group2 = QGroupBox(TRANSLATIONS[self.current_language]["zone2"])
      self.ui_elements["group2"] = group2
      group2.setToolTip(TRANSLATIONS[self.current_language]["zone2_tip"])
      zone2 = QVBoxLayout()
      
      zone2.addWidget(QLabel(TRANSLATIONS[self.current_language]["hip_files"]))
      
      self.hip_list = HipList(self)
      self.hip_list.itemSelectionChanged.connect(self.on_hip_selection_changed)
      self.hip_list.currentItemChanged.connect(self.on_hip_current_changed)
      self.hip_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
      self.hip_list.customContextMenuRequested.connect(self.on_hip_context_menu)
      self.hip_list.setMinimumSize(0, 0)
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
      group2.setMinimumSize(0, 0)
      group2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

      # --- Zone 3 (fixed width) ---
      group3 = QGroupBox(TRANSLATIONS[self.current_language]["zone3"])
      self.ui_elements["group3"] = group3
      group3.setMinimumWidth(ZONE3_FIXED_WIDTH)
      group3.setMaximumWidth(ZONE3_FIXED_WIDTH)
      group3.setMinimumHeight(0)
      group3.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
      group3.setToolTip(TRANSLATIONS[self.current_language]["zone3_tip"])
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
      group4.setToolTip(TRANSLATIONS[self.current_language]["zone4_tip"])
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
      self.rop_list = CompactListWidget()
      self.rop_list.setSelectionMode(QAbstractItemView.MultiSelection)
      self.rop_list.setMinimumSize(0, 0)
      self.rop_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
      group4.setMinimumSize(0, 0)
      group4.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

      self.top_zones_splitter = MainSplitter(Qt.Orientation.Horizontal, queue_handle_indexes=())
      self.top_zones_splitter.addWidget(group2)
      self.top_zones_splitter.addWidget(group3)
      self.top_zones_splitter.addWidget(group4)
      self.top_zones_splitter.setStretchFactor(0, 1)
      self.top_zones_splitter.setStretchFactor(1, 0)
      self.top_zones_splitter.setStretchFactor(2, 1)
      self.top_zones_splitter.setCollapsible(0, False)
      self.top_zones_splitter.setCollapsible(1, False)
      self.top_zones_splitter.setCollapsible(2, False)
      self.top_zones_splitter.setChildrenCollapsible(False)
      self.top_zones_splitter.setSizes([320, ZONE3_FIXED_WIDTH, 320])
      self.top_zones_splitter.configure_handles(
          TRANSLATIONS[self.current_language]["splitter_zones_resize"]
      )

      top_container = QWidget()
      top_container_layout = QVBoxLayout(top_container)
      top_container_layout.setContentsMargins(0, 0, 0, 0)
      top_container_layout.setSpacing(0)
      top_container_layout.addWidget(self.top_zones_splitter)
      top_container.setMinimumSize(0, 0)
      top_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
      self.ui_elements["top_container"] = top_container

      # --- Zone 5 ---
      group5 = QGroupBox(TRANSLATIONS[self.current_language]["zone5"])
      self.ui_elements["group5"] = group5
      group5.setToolTip(TRANSLATIONS[self.current_language]["zone5_tip"])
      zone5 = QVBoxLayout()
      self.render_progress_label = QLabel()
      self.render_progress_label.setStyleSheet("color: #00BFFF; font-size: 12px;")
      self.ui_elements["render_progress_label"] = self.render_progress_label
      zone5.addWidget(self.render_progress_label)
      self.render_progress_bar = QProgressBar()
      self.render_progress_bar.setRange(0, 100)
      self.render_progress_bar.setValue(0)
      self.render_progress_bar.setTextVisible(True)
      self.render_progress_bar.setFormat("%p%")
      self.ui_elements["render_progress_bar"] = self.render_progress_bar
      zone5.addWidget(self.render_progress_bar)
      self.queue_model = RenderQueueModel(TRANSLATIONS[self.current_language]["queue_headers"])
      self.queue_table = RenderQueueView(self)
      self.queue_table.setModel(self.queue_model)
      self.queue_model.data_changed_user.connect(self.on_queue_cell_changed)
      self.queue_table.setColumnWidth(0, 48)
      self.queue_table.setColumnWidth(1, 140)
      self.queue_table.setColumnWidth(2, 120)
      self.queue_table.setColumnWidth(6, 48)
      self.queue_table.setColumnWidth(10, 180)
      self.queue_table.setColumnWidth(COL_SEND2BOT, 56)
      self.queue_table.setColumnWidth(COL_SEND_MP4, 56)
      self.queue_table.setColumnWidth(COL_ETA, 100)
      queue_header = self.queue_table.horizontalHeader()
      queue_header.setStretchLastSection(True)
      queue_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
      queue_header.setMinimumSectionSize(28)
      self.toggle_delegate = ToggleCheckBoxDelegate(
          self.queue_table, on_toggled=self._on_queue_toggle_changed
      )
      self.queue_table.setItemDelegateForColumn(0, self.toggle_delegate)
      self.queue_table.setItemDelegateForColumn(6, self.toggle_delegate)
      self.queue_table.setItemDelegateForColumn(COL_SEND_MP4, self.toggle_delegate)
      self.path_edit_delegate = FullPathEditDelegate(
          self.queue_table, on_committed=self._on_path_cell_committed
      )
      self.status_progress_delegate = StatusProgressDelegate(self.queue_table)
      self.queue_table.setItemDelegateForColumn(COL_HIP, self.path_edit_delegate)
      self.queue_table.setItemDelegateForColumn(COL_OUTPUT, self.path_edit_delegate)
      self.queue_table.setItemDelegateForColumn(COL_STATUS, self.status_progress_delegate)
      self.queue_table.doubleClicked.connect(self._on_queue_double_clicked)
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
      zone5.addWidget(_horizontal_button_bar(btn_layout1, height=36))

      btn_layout2 = QHBoxLayout()
      self.enable_all_btn = QPushButton(TRANSLATIONS[self.current_language]["enable_all"])
      self.ui_elements["enable_all_btn"] = self.enable_all_btn
      self.enable_all_btn.clicked.connect(lambda: self.set_all_queue_enabled(True))
      btn_layout2.addWidget(self.enable_all_btn)

      self.disable_all_btn = QPushButton(TRANSLATIONS[self.current_language]["disable_all"])
      self.ui_elements["disable_all_btn"] = self.disable_all_btn
      self.disable_all_btn.clicked.connect(lambda: self.set_all_queue_enabled(False))
      btn_layout2.addWidget(self.disable_all_btn)

      self.move_up_btn = QPushButton(TRANSLATIONS[self.current_language]["move_up"])
      self.ui_elements["move_up_btn"] = self.move_up_btn
      self.move_up_btn.clicked.connect(self.move_queue_row_up)
      btn_layout2.addWidget(self.move_up_btn)

      self.move_down_btn = QPushButton(TRANSLATIONS[self.current_language]["move_down"])
      self.ui_elements["move_down_btn"] = self.move_down_btn
      self.move_down_btn.clicked.connect(self.move_queue_row_down)
      btn_layout2.addWidget(self.move_down_btn)

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
      zone5.addWidget(_horizontal_button_bar(btn_layout2, height=36))
      group5.setLayout(zone5)
      group5.setMinimumSize(0, 0)
      group5.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

      # --- Log ---
      self.log_output = QTextEdit()
      self.log_output.setReadOnly(True)
      self.log_output.setMinimumSize(0, 0)
      self.log_output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
      self.log_output.setStyleSheet("QTextEdit { background-color: #191919; color: #ffffff; border: 1px solid #555555; }")
      self.log_position_btn = QPushButton()
      self.ui_elements["log_position_btn"] = self.log_position_btn
      self.log_position_btn.setToolTip(TRANSLATIONS[self.current_language]["log_position_tip"])
      self.log_position_btn.clicked.connect(self.toggle_log_position)

      clear_log_btn = QPushButton(TRANSLATIONS[self.current_language]["clear_log"])
      self.ui_elements["clear_log_btn"] = clear_log_btn
      clear_log_btn.clicked.connect(self.clear_log)

      log_btn_row = QHBoxLayout()
      log_btn_row.setContentsMargins(0, 0, 0, 0)
      log_btn_row.setSpacing(6)
      log_btn_row.addWidget(self.log_position_btn)
      log_btn_row.addWidget(clear_log_btn)
      log_btn_row.addStretch()

      self.log_panel = QWidget()
      self.log_panel.setMinimumSize(0, 0)
      log_panel_layout = QVBoxLayout(self.log_panel)
      log_panel_layout.setContentsMargins(0, 0, 0, 0)
      log_panel_layout.setSpacing(4)
      log_panel_layout.addWidget(self.log_output, 1)
      log_panel_layout.addLayout(log_btn_row)

      self.log_position = "bottom"
      self._splitter_states = {"bottom": None, "right": None, "queue": None, "top_zones": None}

      self.queue_splitter = MainSplitter(Qt.Orientation.Vertical, queue_handle_indexes=(0,))
      self.queue_splitter.setMinimumSize(0, 0)
      self.queue_splitter.addWidget(top_container)
      self.queue_splitter.addWidget(group5)
      self.queue_splitter.setStretchFactor(0, 1)
      self.queue_splitter.setStretchFactor(1, 2)

      self.main_splitter = MainSplitter(Qt.Orientation.Vertical, queue_handle_indexes=())
      self.main_splitter.setMinimumSize(0, 0)
      self.main_splitter.addWidget(self.queue_splitter)
      self.main_splitter.addWidget(self.log_panel)
      self.main_splitter.configure_handles(
          TRANSLATIONS[self.current_language]["splitter_queue_resize"]
      )
      self.queue_splitter.configure_handles(
          TRANSLATIONS[self.current_language]["splitter_queue_resize"]
      )
      main_layout.addWidget(self._top_bar)

      self.workflow_guide = QLabel()
      self.workflow_guide.setObjectName("workflowGuide")
      self.workflow_guide.setWordWrap(True)
      self.workflow_guide.setTextFormat(Qt.TextFormat.RichText)
      self.workflow_guide.setMinimumHeight(0)
      self.workflow_guide.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
      self.workflow_guide.setText(TRANSLATIONS[self.current_language]["workflow_html"])
      self.ui_elements["workflow_guide"] = self.workflow_guide
      main_layout.addWidget(self.workflow_guide)
      main_layout.addWidget(self.main_splitter, 1)

      self.all_rops = []
      self._render_jobs = []
      self.load_filters()
      self.restore_window()
      
      # Apply dark theme
      apply_dark_theme(self)
      
      self.main_splitter.setSizes([700, 180])
      self.queue_splitter.setSizes([400, 220])
      self._update_log_position_btn()
      self._apply_layout_resize_policies()
      self._sync_zone1_layout()
      self._update_global_progress(0, 0, -1, "")

  def restore_window(self):
      if os.path.exists(CONFIG_FILE):
          try:
              with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                  data = json.load(f)
              if "language" in data:
                  self.current_language = data["language"]
              if data.get("hython_path"):
                  hython_path = str(data["hython_path"]).strip()
                  if hython_path:
                      if self.houdini_versions.findText(hython_path) < 0:
                          self.houdini_versions.addItem(hython_path)
                      self.houdini_versions.setCurrentText(hython_path)
              if "geometry" in data and data["geometry"]:
                  try:
                      geom = QByteArray.fromHex(data["geometry"].encode())
                      self.restoreGeometry(geom)
                  except Exception as e:
                      self.log_t("geom_restore_error", e=e)
              if "splitter_state" in data and data["splitter_state"]:
                  self._splitter_states["bottom"] = data["splitter_state"]
              ui_cfg = data.get("ui", {})
              if ui_cfg.get("splitter_state_bottom"):
                  self._splitter_states["bottom"] = ui_cfg["splitter_state_bottom"]
              if ui_cfg.get("splitter_state_right"):
                  self._splitter_states["right"] = ui_cfg["splitter_state_right"]
              if ui_cfg.get("queue_splitter_state"):
                  self._splitter_states["queue"] = ui_cfg["queue_splitter_state"]
              if ui_cfg.get("top_zones_splitter_state"):
                  self._splitter_states["top_zones"] = ui_cfg["top_zones_splitter_state"]
              log_pos = ui_cfg.get("log_position", "bottom")
              if log_pos in ("bottom", "right"):
                  self.log_position = log_pos
              if hasattr(self, "main_splitter"):
                  self.main_splitter.setOrientation(
                      Qt.Orientation.Vertical
                      if self.log_position == "bottom"
                      else Qt.Orientation.Horizontal
                  )
                  self._update_log_position_btn()
                  self.queue_splitter.configure_handles(
                      TRANSLATIONS[self.current_language]["splitter_queue_resize"]
                  )
                  self.main_splitter.configure_handles(
                      TRANSLATIONS[self.current_language]["splitter_queue_resize"]
                  )
                  if hasattr(self, "top_zones_splitter"):
                      self.top_zones_splitter.configure_handles(
                          TRANSLATIONS[self.current_language]["splitter_zones_resize"]
                      )
              self._apply_layout_resize_policies()
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
                          self._populate_queue_row(row, entry=entry)
                      self.log_t("queue_restored", count=len(data["queue"]))
          except Exception as e:
              self.log_t("window_restore_error", e=e)
      
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
          self.log_t("column_widths_restore_error", e=e)

      self._restore_layout_splitters()
      
      # Copy hython helper scripts (+ deps) beside .exe before first render
      hython_script_path("render_rop.py")
      hython_script_path("scan_rops.py")
      
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
      self.log_t("tg_preview_warn", msg=msg)
      if hint:
          self.log(f"   {hint}")

  def open_telegram_settings(self):
      from telegram_notifier import (
          reload_config,
          DEFAULT_PREVIEW_MAX_SIDE,
          PREVIEW_MIN_SIDE,
          PREVIEW_MAX_SIDE_LIMIT,
      )

      t = TRANSLATIONS[self.current_language]
      dlg = QDialog(self)
      dlg.setWindowTitle(t["tg_dialog_title"])
      dlg.setMinimumWidth(520)
      apply_dark_theme(dlg)
      layout = QVBoxLayout(dlg)

      instructions = QLabel(t["tg_instructions_html"])
      instructions.setWordWrap(True)
      instructions.setTextFormat(Qt.TextFormat.RichText)
      instructions.setObjectName("tgInstructions")
      scroll = QScrollArea()
      scroll.setWidgetResizable(True)
      scroll.setFrameShape(QScrollArea.Shape.NoFrame)
      scroll.setWidget(instructions)
      scroll.setMaximumHeight(220)
      layout.addWidget(scroll)

      token_input = QLineEdit()
      token_input.setPlaceholderText("123456789:ABCdefGHI...")
      chat_input = QLineEdit()
      chat_input.setPlaceholderText("-1001234567890")
      preview_max_spin = QSpinBox()
      preview_max_spin.setRange(PREVIEW_MIN_SIDE, PREVIEW_MAX_SIDE_LIMIT)
      preview_max_spin.setSingleStep(100)
      preview_max_spin.setValue(DEFAULT_PREVIEW_MAX_SIDE)

      mp4_on_complete = QCheckBox(t["tg_mp4_on_complete"])
      mp4_on_complete.setChecked(True)
      mp4_use_preview = QCheckBox(t["tg_mp4_use_preview"])
      mp4_use_preview.setChecked(True)
      mp4_max_spin = QSpinBox()
      mp4_max_spin.setRange(0, PREVIEW_MAX_SIDE_LIMIT)
      mp4_max_spin.setSingleStep(100)
      mp4_max_spin.setValue(0)

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
              mp4_on_complete.setChecked(bool(tg.get("send_mp4_on_complete", True)))
              mp4_use_preview.setChecked(bool(tg.get("mp4_use_preview_max_side", True)))
              try:
                  mp4_max_spin.setValue(int(tg.get("mp4_max_side", 0)))
              except (TypeError, ValueError):
                  mp4_max_spin.setValue(0)
          except json.JSONDecodeError:
              pass

      def sync_mp4_spin():
          mp4_max_spin.setEnabled(not mp4_use_preview.isChecked())

      mp4_use_preview.toggled.connect(sync_mp4_spin)
      sync_mp4_spin()

      layout.addWidget(QLabel(t["bot_token"]))
      layout.addWidget(token_input)
      layout.addWidget(QLabel(t["chat_id"]))
      layout.addWidget(chat_input)
      layout.addWidget(QLabel(t["tg_preview_max"]))
      layout.addWidget(preview_max_spin)
      hint = QLabel(t["tg_preview_hint"])
      hint.setWordWrap(True)
      layout.addWidget(hint)
      layout.addWidget(mp4_on_complete)
      layout.addWidget(mp4_use_preview)
      layout.addWidget(QLabel(t["tg_mp4_max_side"]))
      layout.addWidget(mp4_max_spin)

      btn_row = QHBoxLayout()
      save_btn = QPushButton(t["save"])
      check_btn = QPushButton(t["check_bot"])
      test_btn = QPushButton(t["send_test"])
      btn_row.addWidget(save_btn)
      btn_row.addWidget(check_btn)
      btn_row.addWidget(test_btn)
      layout.addLayout(btn_row)

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
          data["telegram"]["bot_token"] = token_input.text().strip()
          data["telegram"]["chat_id"] = chat_input.text().strip()
          data["telegram"]["preview_max_side"] = preview_max_spin.value()
          data["telegram"]["send_mp4_on_complete"] = mp4_on_complete.isChecked()
          data["telegram"]["mp4_use_preview_max_side"] = mp4_use_preview.isChecked()
          data["telegram"]["mp4_max_side"] = mp4_max_spin.value()
          with open(CONFIG_FILE, "w", encoding="utf-8") as f:
              json.dump(data, f, indent=4, ensure_ascii=False)
          reload_config()
          dlg.accept()
          self.log(t["tg_saved"])

      def check_bot():
          token = token_input.text().strip()
          if not token:
              self.log_t("tg_token_empty")
              return
          ok, err = test_bot_connection(bot_token=token)
          if ok:
              self.log_t("tg_bot_ok")
          else:
              self.log_t("tg_bot_check_fail", err=err)

      def send_test_message():
          token = token_input.text().strip()
          chat_id = chat_input.text().strip()
          if not token or not chat_id:
              self.log_t("tg_creds_missing")
              return
          ok, err = send_message(
              "🚀 Test message from Houdini Render Manager!",
              bot_token=token,
              chat_id=chat_id,
          )
          if ok:
              self.log_t("tg_test_ok")
          else:
              self.log_t("tg_send_fail", err=err)

      save_btn.clicked.connect(save_cfg)
      check_btn.clicked.connect(check_bot)
      test_btn.clicked.connect(send_test_message)
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
          self.log_t("hython_selected", file=file)

  def check_environment(self):
      path = self.houdini_versions.currentText()
      if os.path.exists(path):
          self.log_t("houdini_found", path=path)
      else:
          self.log_t("houdini_not_found", path=path)

      from telegram_notifier import check_preview_dependencies

      ok, msg, hint = check_preview_dependencies()
      if ok:
          self.log_t("preview_deps_ok")
      else:
          self.log_t("preview_deps_fail", msg=msg)
          if hint:
              self.log(f"   {hint}")

  def _sync_zone1_layout(self):
      """Let hython path field shrink so zone 1 buttons fit without a scrollbar."""
      if not hasattr(self, "houdini_versions"):
          return
      min_chars = 4 if self.current_language == "ru" else 6
      self.houdini_versions.setMinimumContentsLength(min_chars)
      if hasattr(self, "_zone1_btns_widget"):
          self._zone1_btns_widget.adjustSize()
      self.houdini_versions.updateGeometry()
      if hasattr(self, "ui_elements") and "group1" in self.ui_elements:
          self.ui_elements["group1"].updateGeometry()

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
      if "houdini_version_label" in self.ui_elements:
          self.ui_elements["houdini_version_label"].setText(t["houdini_version"])
      self.ui_elements["group1"].setTitle(t["zone1"])
      self.ui_elements["group2"].setTitle(t["zone2"])
      self.ui_elements["group3"].setTitle(t["zone3"])
      self.ui_elements["group4"].setTitle(t["zone4"])
      self.ui_elements["group5"].setTitle(t["zone5"])
      if hasattr(self, "main_splitter"):
          self.main_splitter.configure_handles(t["splitter_queue_resize"])
      if hasattr(self, "queue_splitter"):
          self.queue_splitter.configure_handles(t["splitter_queue_resize"])
      if hasattr(self, "top_zones_splitter"):
          self.top_zones_splitter.configure_handles(t["splitter_zones_resize"])
      self._update_log_position_btn()
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
      self.ui_elements["move_up_btn"].setText(t["move_up"])
      self.ui_elements["move_down_btn"].setText(t["move_down"])
      self.ui_elements["open_hip_btn"].setText(t["open_hip"])
      self.ui_elements["open_output_btn"].setText(t["open_output"])
      self.ui_elements["duplicate_btn"].setText(t["duplicate"])
      
      self.queue_table.setHorizontalHeaderLabels(t["queue_headers"])
      self.queue_model.set_headers(t["queue_headers"])
      if hasattr(self, "workflow_guide"):
          self.workflow_guide.setText(t["workflow_html"])
      for key, tip_key in (
          ("group2", "zone2_tip"),
          ("group3", "zone3_tip"),
          ("group4", "zone4_tip"),
          ("group5", "zone5_tip"),
      ):
          if key in self.ui_elements:
              self.ui_elements[key].setToolTip(t[tip_key])
      self.update_hip_scan_label()
      self.update_rop_count_label()
      self._sync_zone1_layout()
      if self.queue_thread and self.queue_thread.isRunning():
          self._update_eta_displays()

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
          self.log_t("output_path_set", path=path)
      if self.initialized:
          self.save_state()

  def _set_path_cell(self, row, col, path, hip_file=None, op_name=None):
      """Update path cell display without treating it as user edit."""
      self._queue_cell_edit_guard = True
      try:
          self.queue_model.set_path(row, col, path, hip_file=hip_file, op_name=op_name)
      finally:
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
          self.queue_model.set_enabled(row, enabled)
      if self.initialized:
          self.save_state()

  def _get_selected_queue_row(self):
      indexes = self.queue_table.selectedIndexes()
      return indexes[0].row() if indexes else None

  def open_selected_hip(self):
      row = self._get_selected_queue_row()
      if row is None:
          self.log_t("select_queue_row")
          return
      path = self._get_cell_path(self.queue_table.item(row, COL_HIP))
      if path and os.path.isfile(path):
          os.startfile(path)
      else:
          self.log_t("hip_not_found", path=path)

  def open_selected_output_folder(self):
      row = self._get_selected_queue_row()
      if row is None:
          self.log_t("select_queue_row")
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
          self.log_t("folder_not_found", folder=folder)

  def _read_base_resolution(self, row):
      return self.queue_model.read_base_resolution(row)

  def _set_base_resolution(self, row, base_x, base_y):
      self.queue_model.set_resize(
          row,
          self.queue_model.get_text(row, 9) or "100%",
          base_x=base_x,
          base_y=base_y,
      )

  def _parse_resize_pct(self, resize_text):
      if not resize_text:
          return 100.0
      text = str(resize_text).strip().rstrip("%")
      try:
          return float(text) if text else 100.0
      except ValueError:
          return 100.0

  def _resolve_render_size(self, row, base_x=None, base_y=None):
      return self.queue_model.resolve_render_size(row, base_x=base_x, base_y=base_y)

  def _apply_resize_display(self, row, base_x=None, base_y=None):
      if base_x is not None or base_y is not None:
          bx, by = self.queue_model.read_base_resolution(row)
          self.queue_model.set_resize(
              row,
              self.queue_model.get_text(row, 9) or "100%",
              base_x=base_x if base_x is not None else bx,
              base_y=base_y if base_y is not None else by,
          )
      return self.queue_model.resolve_render_size(row)

  def _update_global_progress(self, cur, total, row, status):
      t = TRANSLATIONS[self.current_language]
      if total <= 0 or not status:
          self.render_progress_label.setText(t["render_progress_idle"])
          self.render_progress_bar.setValue(0)
          self.render_progress_bar.setFormat("%p%")
          self.setWindowTitle(t["title"])
          return

      hip = "?"
      rop = "?"
      if row >= 0:
          hip_path = self.queue_model.get_path(row, COL_HIP)
          if hip_path:
              hip = os.path.basename(hip_path)
          rop = self.queue_model.get_text(row, COL_ROP) or "?"

      pct = 0
      if status == "Running" and self._render_job_total > 0:
          pct = int(
              ((self._jobs_done + self._active_render_ratio) / self._render_job_total) * 100
          )
          pct = max(0, min(100, pct))
      elif self._render_job_total > 0:
          pct = int((self._jobs_done / self._render_job_total) * 100)

      self.render_progress_bar.setValue(pct)
      self.render_progress_label.setText(
          t["render_progress"].format(
              cur=cur, total=total, hip=hip, rop=rop, status=status, pct=pct
          )
      )
      self.setWindowTitle(f"{t['title']} — {status} ({cur}/{total})")

  def _apply_row_progress(self, row, ratio):
      try:
          ratio = max(0.0, min(1.0, float(ratio)))
      except (TypeError, ValueError):
          ratio = 0.0
      meta = self._row_eta_meta.get(row, {})
      if meta.get("skip") and meta.get("work_total", 0) > 0:
          ratio = max(self._row_work_ratio.get(row, 0.0), ratio)
          self._row_work_ratio[row] = ratio
      self._active_render_ratio = ratio
      self._set_status_render_progress(row, ratio)
      cur = min(self._jobs_done + 1, self._render_job_total) if self._render_job_total else 1
      self._update_global_progress(cur, self._render_job_total, row, "Running")

  def _on_frame_rendered(self, row, work_done, work_total, frame_seconds=-1.0):
      """Update ETA when a frame finishes; use Redshift per-frame total when available."""
      try:
          work_done = int(work_done)
          work_total = int(work_total)
      except (TypeError, ValueError):
          return
      if work_total <= 0 or work_done <= 0:
          return
      prev = self._row_work_done.get(row, 0)
      if work_done <= prev:
          return
      now = time.monotonic()
      frame_sec = None
      try:
          if frame_seconds is not None and float(frame_seconds) > 0:
              frame_sec = float(frame_seconds)
      except (TypeError, ValueError):
          frame_sec = None
      if frame_sec is None:
          start = self._row_render_start.get(row)
          if start is not None:
              if prev > 0:
                  frame_sec = now - self._row_last_frame_mono.get(row, start)
              else:
                  frame_sec = now - start
      if frame_sec and frame_sec > 0:
          samples = self._row_frame_seconds.setdefault(row, [])
          samples.append(frame_sec)
      self._row_last_frame_mono[row] = now
      self._row_work_done[row] = work_done
      meta = self._row_eta_meta.setdefault(row, {})
      meta["work_total"] = work_total
      self._update_eta_displays()

  def _sec_per_frame_estimate(self, row):
      work_done = self._row_work_done.get(row, 0)
      meta = self._row_eta_meta.get(row, {})
      work_total = meta.get("work_total", 0)
      if work_done <= 0 or work_total <= 0:
          return None
      times = self._row_frame_seconds.get(row, [])
      if not times:
          return None
      last = times[-1]
      if len(times) == 1:
          return last
      avg = sum(times) / len(times)
      return 0.65 * avg + 0.35 * last

  def _remaining_current_job_seconds(self):
      cur = self._progress_ui_row
      if cur < 0:
          return None
      meta = self._row_eta_meta.get(cur, {})
      work_done = self._row_work_done.get(cur, 0)
      work_total = meta.get("work_total", 0)
      if work_total > 0 and work_done >= work_total:
          return 0
      if work_done <= 0:
          return None
      sec_per = self._sec_per_frame_estimate(cur)
      if not sec_per or sec_per <= 0:
          return None
      return sec_per * (work_total - work_done)

  def _avg_job_seconds(self):
      if not self._job_duration_samples:
          return None
      return sum(self._job_duration_samples) / len(self._job_duration_samples)

  def _estimate_job_seconds(self, row):
      meta = self._row_eta_meta.get(row, {})
      work = meta.get("work_total")
      if work is not None and work <= 0:
          return 1.0
      avg = self._avg_job_seconds()
      if avg and avg > 0:
          return avg
      cur = self._progress_ui_row
      if cur >= 0:
          sec_per = self._sec_per_frame_estimate(cur)
          if sec_per and sec_per > 0 and work:
              return sec_per * work
      return None

  def _eta_tip(self, seconds):
      finish = finish_clock_from_now(seconds)
      if not finish:
          return ""
      remaining = format_remaining_seconds(seconds)
      return TRANSLATIONS[self.current_language]["eta_finish_tip"].format(
          remaining=remaining, finish=finish
      )

  def _set_row_eta(self, row, seconds, pending=False):
      if seconds is None or seconds <= 0:
          text = "..." if pending else "--"
          self.queue_model.set_eta_display(row, text)
          return
      self.queue_model.set_eta_display(
          row,
          format_eta_finish_cell(seconds),
          self._eta_tip(seconds),
      )

  def _update_eta_displays(self):
      batch = self._active_render_rows
      if not batch or not self.queue_thread or not self.queue_thread.isRunning():
          return

      cur = self._progress_ui_row
      try:
          cur_idx = batch.index(cur) if cur in batch else -1
      except ValueError:
          cur_idx = -1
      cur_remaining = self._remaining_current_job_seconds()

      batch_set = set(batch)
      for row in range(self.queue_table.rowCount()):
          if row not in batch_set:
              self.queue_model.set_eta_display(row, "--")
              continue

          status = self.queue_model.get_text(row, COL_STATUS)
          if status in ("Completed", "Skipped", "Failed", "Stopped"):
              self.queue_model.set_eta_display(row, "--")
              continue

          try:
              idx = batch.index(row)
          except ValueError:
              self.queue_model.set_eta_display(row, "--")
              continue

          if cur_idx < 0:
              self._set_row_eta(row, None, pending=True)
              continue

          if idx < cur_idx:
              self.queue_model.set_eta_display(row, "--")
              continue

          if row == cur:
              self._set_row_eta(row, cur_remaining, pending=True)
              continue

          wait = cur_remaining or 0
          for j in range(cur_idx + 1, idx):
              est = self._estimate_job_seconds(batch[j])
              if est:
                  wait += est
          est_self = self._estimate_job_seconds(row)
          if est_self:
              wait += est_self
          self._set_row_eta(row, wait if wait > 0 else None, pending=True)

  def _clear_all_eta_displays(self):
      for row in range(self.queue_table.rowCount()):
          self.queue_model.set_eta_display(row, "--")

  def _start_eta_tracking(self, queue_data):
      self._active_render_rows = [item["row"] for item in queue_data]
      self._row_render_start = {}
      self._job_duration_samples = []
      self._row_eta_meta = {}
      self._row_work_ratio = {}
      self._row_work_done = {}
      self._row_last_frame_mono = {}
      self._row_frame_seconds = {}
      for item in queue_data:
          row = item["row"]
          skip = item["skip_val"] == "1"
          work_total = item.get(
              "work_total", item["end_frame"] - item["start_frame"] + 1
          )
          self._row_eta_meta[row] = {"skip": skip, "work_total": work_total}
      self._clear_all_eta_displays()

  def _stop_eta_tracking(self):
      self._active_render_rows = []
      self._row_render_start = {}
      self._job_duration_samples = []
      self._row_eta_meta = {}
      self._row_work_ratio = {}
      self._row_work_done = {}
      self._row_last_frame_mono = {}
      self._row_frame_seconds = {}
      self._clear_all_eta_displays()

  def update_rop_count_label(self):
      t = TRANSLATIONS[self.current_language]
      total = len(self.all_rops)
      shown = self.rop_list.count()
      self.rop_count_label.setText(t["rop_count"].format(shown=shown, total=total))

  def _populate_queue_row(self, row, entry=None, rop_name=None, rop_type=None, rop_data=None, hip_path=None):
      """Fill one queue row via QAbstractTableModel."""
      if entry is not None:
          self.queue_model.insert_entry(row, entry)
          return
      if not hip_path:
          if rop_data and rop_data.get("hip"):
              hip_path = rop_data.get("hip")
          elif self.last_scanned_hip:
              hip_path = self.last_scanned_hip
          else:
              hip_path = self.get_active_hip_path() or ""
      new_entry = _empty_row()
      new_entry["enabled"] = "1"
      new_entry["skip"] = "1" if (rop_data and rop_data.get("skip_existing")) else "0"
      new_entry["hip"] = hip_path
      new_entry["rop"] = rop_name or ""
      new_entry["type"] = rop_type or ""
      new_entry["start_frame"] = str(rop_data.get("start_frame", "1")) if rop_data else "1"
      new_entry["end_frame"] = str(rop_data.get("end_frame", "100")) if rop_data else "100"
      sx = str(rop_data.get("size_x", "1920")) if rop_data else "1920"
      sy = str(rop_data.get("size_y", "1080")) if rop_data else "1080"
      new_entry["size_x_base"] = sx
      new_entry["size_y_base"] = sy
      new_entry["resize"] = "100%"
      new_entry["output_path"] = (rop_data.get("output_path", "") if rop_data else "").strip()
      new_entry["status"] = "Queued"
      import telegram_notifier as tg
      tg.reload_config()
      new_entry["send_mp4"] = "1" if tg.SEND_MP4_ON_COMPLETE else "0"
      self.queue_model.insert_entry(row, new_entry)

  def save_settings(self):
      self.save_state()
      self.log_t("settings_saved")

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
      menu.addAction(t["ctx_move_up"], lambda: self.move_queue_row_up(row))
      menu.addAction(t["ctx_move_down"], lambda: self.move_queue_row_down(row))
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
              self.log_t("cant_reset_running")
              return
      self.queue_model.reset_status_row(row)
      if self.initialized:
          self.save_state()
      rop_name = self.queue_model.get_text(row, COL_ROP) or "?"
      self.log_t("status_reset", rop_name=rop_name)

  def _context_set_enabled(self, row, enabled):
      self.queue_model.set_enabled(row, enabled)
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
      if self.queue_model.rowCount() > 0:
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
          self.log_t("no_rops_selected")
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
          self._populate_queue_row(
              row, rop_name=rop_name, rop_type=rop_type, rop_data=rop_data, hip_path=hip_path
          )
          if not self.queue_model.get_path(row, COL_OUTPUT):
              self.log_t(
                  "rop_path_empty",
                  rop_name=rop_name,
                  detail=TRANSLATIONS[self.current_language]["path_empty"],
              )
          added += 1

      self.log_t("rops_added", count=added)
      self.update_start_button()
      self.save_state()

  def _splitter_state_hex(self, splitter):
      try:
          return splitter.saveState().toHex().data().decode()
      except Exception:
          return ""

  def _restore_splitter_state_hex(self, splitter, hex_state):
      if not hex_state:
          return
      try:
          splitter.restoreState(QByteArray.fromHex(hex_state.encode()))
      except Exception as e:
          self.log_t("splitter_restore_error", e=e)

  def _restore_layout_splitters(self):
      if not hasattr(self, "main_splitter"):
          return
      self._restore_splitter_state_hex(
          self.main_splitter, self._splitter_states.get(self.log_position)
      )
      self._restore_splitter_state_hex(
          self.queue_splitter, self._splitter_states.get("queue")
      )
      self._restore_splitter_state_hex(
          self.top_zones_splitter, self._splitter_states.get("top_zones")
      )

  def _apply_layout_resize_policies(self):
      log_right = self.log_position == "right"
      if hasattr(self, "log_panel"):
          self.log_panel.setMinimumWidth(80 if log_right else 0)
          self.log_panel.setSizePolicy(
              QSizePolicy.Policy.Expanding,
              QSizePolicy.Policy.Expanding,
          )
      if hasattr(self, "queue_splitter"):
          self.queue_splitter.setSizePolicy(
              QSizePolicy.Policy.Expanding,
              QSizePolicy.Policy.Expanding,
          )
      if hasattr(self, "main_splitter"):
          self.main_splitter.setStretchFactor(0, 4 if log_right else 1)
          self.main_splitter.setStretchFactor(1, 1)

  def _update_log_position_btn(self):
      if not hasattr(self, "log_position_btn"):
          return
      t = TRANSLATIONS[self.current_language]
      key = "log_position_right" if self.log_position == "right" else "log_position_bottom"
      self.log_position_btn.setText(t[key])
      self.log_position_btn.setToolTip(t["log_position_tip"])

  def toggle_log_position(self):
      self.set_log_position("right" if self.log_position == "bottom" else "bottom")

  def set_log_position(self, position, save=True):
      if position not in ("bottom", "right"):
          position = "bottom"
      if hasattr(self, "main_splitter"):
          current = self._splitter_state_hex(self.main_splitter)
          if current:
              self._splitter_states[self.log_position] = current
          queue_state = self._splitter_state_hex(self.queue_splitter)
          if queue_state:
              self._splitter_states["queue"] = queue_state
      self.log_position = position
      orient = (
          Qt.Orientation.Vertical
          if position == "bottom"
          else Qt.Orientation.Horizontal
      )
      self.main_splitter.setOrientation(orient)
      self._apply_layout_resize_policies()
      self._restore_splitter_state_hex(
          self.main_splitter, self._splitter_states.get(position)
      )
      self._update_log_position_btn()
      QTimer.singleShot(0, self.updateGeometry)
      if save and self.initialized:
          self.save_state()

  def clear_log(self):
      self.log_output.clear()
      self.log_t("log_cleared")

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
                  
                  splitter_hex = self._splitter_state_hex(self.main_splitter)
                  if splitter_hex:
                      data["splitter_state"] = splitter_hex
                      if "ui" not in data:
                          data["ui"] = {}
                      key = (
                          "splitter_state_bottom"
                          if self.log_position == "bottom"
                          else "splitter_state_right"
                      )
                      data["ui"][key] = splitter_hex
                      data["ui"]["log_position"] = self.log_position
                      queue_hex = self._splitter_state_hex(self.queue_splitter)
                      if queue_hex:
                          data["ui"]["queue_splitter_state"] = queue_hex
                      top_zones_hex = self._splitter_state_hex(self.top_zones_splitter)
                      if top_zones_hex:
                          data["ui"]["top_zones_splitter_state"] = top_zones_hex
          except Exception as e:
              self.log_t("save_geom_error", e=e)
          
          # Save queue table column widths
          try:
              if "ui" not in data:
                  data["ui"] = {}
              data["ui"]["column_widths"] = [self.queue_table.columnWidth(i) for i in range(self.queue_table.columnCount())]
          except Exception as e:
              self.log_t("save_columns_error", e=e)

          # Write config with explicit encoding
          with open(CONFIG_FILE, "w", encoding="utf-8") as f:
              json.dump(data, f, indent=4, ensure_ascii=False)
      except Exception as e:
          self.log_t("save_state_error", e=e)

  def _sync_hython_config(self):
      """Write current hython combo value to config.json (run_render reads it from disk)."""
      path = self.houdini_versions.currentText().strip()
      try:
          data = {}
          if os.path.exists(CONFIG_FILE):
              with open(CONFIG_FILE, encoding="utf-8") as f:
                  data = json.load(f)
          data["hython_path"] = path
          with open(CONFIG_FILE, "w", encoding="utf-8") as f:
              json.dump(data, f, indent=4, ensure_ascii=False)
      except Exception as e:
          self.log_t("hython_save_fail", e=e)
      return path

  def start_render(self):
      if self.queue_model.rowCount() == 0:
          self.log_t("queue_empty")
          return
      if self.queue_thread and self.queue_thread.isRunning():
          self.log_t("queue_running")
          return

      hython_path = self._sync_hython_config()
      if not hython_path or not os.path.exists(hython_path):
          self.log_t(
              "hython_missing",
              path=hython_path or log_msg(self.current_language, "hython_not_selected"),
          )
          self.log_t("hython_select_hint")
          return

      queue_data = []
      for row in range(self.queue_model.rowCount()):
          entry = self.queue_model.row_to_entry(row)
          if not is_toggle_checked_value(entry.get("enabled")):
              self.log_t("row_disabled", row=row + 1)
              continue

          hip_file = str(entry.get("hip", "") or "").strip()
          rop_name = str(entry.get("rop", "") or "").strip()
          rop_type = str(entry.get("type", "") or "").strip()
          output_path = str(entry.get("output_path", "") or "").strip()
          skip_val = "1" if is_toggle_checked_value(entry.get("skip")) else "0"

          try:
              send2bot = int(entry.get("send2bot", 0) or 0)
              if send2bot < 0:
                  send2bot = 0
          except (TypeError, ValueError):
              send2bot = 0

          send_mp4 = is_toggle_checked_value(entry.get("send_mp4"))

          if not hip_file or not rop_name:
              self.log_t("row_no_hip_rop", row=row + 1)
              continue

          if not os.path.isfile(hip_file):
              self.log_t("row_hip_missing", row=row + 1, hip_file=hip_file)
              continue

          if not output_path:
              self.log_t(
                  "row_path_empty",
                  row=row + 1,
                  rop_name=rop_name,
                  detail=TRANSLATIONS[self.current_language]["path_empty"],
              )

          try:
              start_frame = int(entry.get("start_frame", 1) or 1)
              end_frame = int(entry.get("end_frame", 100) or 100)
          except (TypeError, ValueError):
              self.log_t("row_bad_frames", row=row + 1)
              start_frame = 1
              end_frame = 100

          base_x, base_y, resize_pct, actual_x, actual_y = self.queue_model.resolve_render_size(row)

          work_total = end_frame - start_frame + 1
          if skip_val == "1" and output_path:
              work_total = len(
                  missing_render_frames(
                      output_path, start_frame, end_frame, hip_file, rop_name
                  )
              )

          queue_data.append({
              "row": row,
              "hip_file": hip_file,
              "rop_name": rop_name,
              "rop_type": rop_type,
              "start_frame": start_frame,
              "end_frame": end_frame,
              "skip_val": skip_val,
              "work_total": work_total,
              "size_x": base_x,
              "size_y": base_y,
              "resize_pct": resize_pct,
              "render_width": actual_x,
              "render_height": actual_y,
              "output_path": output_path,
              "send2bot": send2bot,
              "send_mp4": send_mp4,
          })

      if not queue_data:
          self.log_t("no_enabled_jobs")
          return

      self.log_t("render_start", count=len(queue_data))
      self._jobs_done = 0
      self._active_render_ratio = 0.0
      self._progress_ui_row = -1
      self._render_job_total = len(queue_data)
      self._start_eta_tracking(queue_data)
      self.stop_btn.setEnabled(True)
      set_delete_style(self.stop_btn)
      self.start_btn.setEnabled(False)
      set_disabled_style(self.start_btn)

      self._render_jobs = queue_data
      self.queue_thread = RenderQueueWorker(queue_data, language=self.current_language)
      conn = Qt.ConnectionType.QueuedConnection
      self.queue_thread.log_signal.connect(self.log, conn)
      self.queue_thread.update_row_signal.connect(self.on_worker_update_row, conn)
      self.queue_thread.progress_signal.connect(self.on_render_progress, conn)
      self.queue_thread.frame_progress_signal.connect(self.on_render_frame_progress, conn)
      self.queue_thread.finished_signal.connect(self.on_queue_finished, conn)
      self.queue_thread.start()
      self.log_t("thread_started", count=len(queue_data))

  def _set_status_render_progress(self, row, ratio=None):
      if ratio is None:
          self.queue_model.set_status(
              row, self.queue_model.get_text(row, COL_STATUS), progress=None
          )
      else:
          self.queue_model.set_status(row, "Running", progress=float(ratio))

  def _clear_all_status_render_progress(self):
      for row in range(self.queue_table.rowCount()):
          if self.queue_model.data(
              self.queue_model.index(row, COL_STATUS), RENDER_PROGRESS_ROLE
          ) is not None:
              self.queue_model.set_status(
                  row, self.queue_model.get_text(row, COL_STATUS), progress=None
              )

  def on_render_frame_progress(self, row, ratio, work_done, work_total, frame_seconds):
      self._apply_row_progress(row, ratio)
      if work_done > 0:
          self._on_frame_rendered(row, work_done, work_total, frame_seconds)

  def on_render_progress(self, cur, total, row):
      self._render_job_cur = cur
      self._render_job_total = total
      if self._progress_ui_row != row:
          self._active_render_ratio = 0.0
          for r in range(self.queue_table.rowCount()):
              if r != row:
                  self._set_status_render_progress(r, None)
          self._set_status_render_progress(row, 0.0)
      self._progress_ui_row = row
      self._update_global_progress(cur, total, row, "Running")
      self._update_eta_displays()
      self.queue_table.selectRow(row)
      scroll_item = self.queue_table.item(row, 0)
      if scroll_item:
          self.queue_table.scrollToItem(scroll_item)

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
      self.log_t("stop_attempt")
      if self.queue_thread and self.queue_thread.isRunning():
          self.queue_thread.requestInterruption()
      if stop_render():
          self.log_t("render_stopped")
          for row in range(self.queue_table.rowCount()):
              if self.queue_model.get_text(row, COL_STATUS) == "Running":
                  self.queue_model.set_status(row, "Stopped", progress=None)
          self._clear_all_status_render_progress()
          self._render_job_cur = 0
          self._render_job_total = 0
          self._jobs_done = 0
          self._active_render_ratio = 0.0
          self._progress_ui_row = -1
          self._stop_eta_tracking()
          self._update_global_progress(0, 0, -1, "")
          self.save_state()
      else:
          self.log_t("render_not_running")

      self.stop_btn.setEnabled(False)
      set_disabled_style(self.stop_btn)
      self.update_start_button()

  def on_worker_update_row(self, row, status, start_time, end_time):
      if status == "Running":
          self._row_render_start[row] = time.monotonic()
          self._row_work_done[row] = 0
          self._row_last_frame_mono.pop(row, None)
          self._row_frame_seconds.pop(row, None)
          self._set_status_render_progress(row, 0.0)
          self.queue_model.set_times(row, start_time=start_time, end_time="")
          self._update_eta_displays()
          return
      start_mono = self._row_render_start.pop(row, None)
      if start_mono and status == "Completed":
          dur = time.monotonic() - start_mono
          if dur >= 1.0:
              self._job_duration_samples.append(dur)
      self._row_work_ratio.pop(row, None)
      self._set_status_render_progress(row, None)
      self.queue_model.set_status(row, status, progress=None)
      if status in ("Completed", "Skipped", "Failed", "Stopped"):
          self._jobs_done += 1
          self._active_render_ratio = 0.0
          if self.queue_thread and self.queue_thread.isRunning():
              cur = min(self._jobs_done, self._render_job_total)
              self._update_global_progress(cur, self._render_job_total, row, status)
      st = start_time or self.queue_model.get_text(row, COL_START_TIME)
      et = end_time
      duration = format_duration_hms(st, et) if st and et else "--"
      self.queue_model.set_times(
          row,
          start_time=start_time if start_time else None,
          end_time=end_time if end_time else None,
          duration=duration,
      )
      self._update_eta_displays()

  def on_queue_finished(self, cancelled):
      if cancelled:
          self.log_t("queue_cancelled")
      else:
          self.log_t("queue_done")
      self.queue_thread = None
      self._render_jobs = []
      self._clear_all_status_render_progress()
      self._render_job_cur = 0
      self._render_job_total = 0
      self._jobs_done = 0
      self._active_render_ratio = 0.0
      self._progress_ui_row = -1
      self._stop_eta_tracking()
      self._update_global_progress(0, 0, -1, "")
      self.stop_btn.setEnabled(False)
      set_disabled_style(self.stop_btn)
      self.update_start_button()
      self.save_state()

  def _collect_queue_entries(self):
      return self.queue_model.all_entries()

  def _restore_queue_entries(self, entries):
      self.queue_model.load_entries(entries)
      self.update_start_button()
      self.on_queue_selection_changed()

  def _move_queue_row(self, src_row, dest_row):
      if self.queue_thread and self.queue_thread.isRunning():
          self.log(TRANSLATIONS[self.current_language]["queue_reorder_blocked"])
          return
      if self.queue_model.move_row(src_row, dest_row):
          self.queue_table.selectRow(min(src_row, dest_row))
          if self.initialized:
              self.save_state()

  def move_queue_row_up(self, row=None):
      if row is None:
          row = self._get_selected_queue_row()
      if row is None or row <= 0:
          return
      self._move_queue_row(row, row - 1)

  def move_queue_row_down(self, row=None):
      if row is None:
          row = self._get_selected_queue_row()
      if row is None or row >= self.queue_table.rowCount() - 1:
          return
      self._move_queue_row(row, row + 2)

  def _queue_row_to_entry(self, row):
      return self.queue_model.row_to_entry(row)

  def duplicate_queue_row(self, row=None):
      if row is None:
          selected = self.queue_table.selectedIndexes()
          if not selected:
              self.log_t("select_queue_row")
              return
          row = selected[0].row()
      entry = self._queue_row_to_entry(row)
      entry["status"] = "Queued"
      entry["start_time"] = ""
      entry["end_time"] = ""
      entry["duration"] = "--"
      new_row = row + 1
      self._populate_queue_row(new_row, entry=entry)
      self.queue_table.selectRow(new_row)
      self.update_start_button()
      self.on_queue_selection_changed()
      if self.initialized:
          self.save_state()
      rop_name = entry.get("rop", "?")
      self.log_t("duplicate_added", row=new_row + 1, rop_name=rop_name)

  def reset_rop(self):
      selected_rows = self.queue_table.selectedIndexes()
      if not selected_rows:
          self.log_t("select_queue_row")
          return
      row = selected_rows[0].row()
      
      rop_name = self.queue_model.get_text(row, COL_ROP)
      if not rop_name:
          return
      
      hip_file = self.queue_model.get_path(row, COL_HIP)
      
      if not hip_file:
          self.log_t("hip_not_for_rop")
          return

      self.log_t("rop_reset_read", rop_name=rop_name, hip=os.path.basename(hip_file))
      
      # Run scan to get latest data
      rops_data, error = self._run_scan(hip_file)
      if error:
          self.log_t("read_error", error=error)
          return
      
      rop_data = next((r for r in rops_data if r["name"] == rop_name), None)
      
      if rop_data:
          start_frame = str(rop_data.get("start_frame", "1"))
          end_frame = str(rop_data.get("end_frame", "100"))
          self.queue_model.set_field(row, "start_frame", start_frame)
          self.queue_model.set_field(row, "end_frame", end_frame)
          self.queue_model.set_field(
              row, "skip", "1" if rop_data.get("skip_existing") else "0"
          )
          size_x = str(rop_data.get("size_x", "1920"))
          size_y = str(rop_data.get("size_y", "1080"))
          self.queue_model.set_resize(row, "100%", base_x=size_x, base_y=size_y)
          output_path = rop_data.get("output_path", "")
          self.queue_model.set_path(
              row, COL_OUTPUT, output_path, hip_file=hip_file, op_name=rop_name
          )
          self.queue_model.reset_status_row(row)
          
          self.save_state()
          self.log_t(
              "rop_reset_ok",
              start_frame=start_frame,
              end_frame=end_frame,
              size_x=size_x,
              size_y=size_y,
          )
      else:
          self.log_t("rop_not_in_file", rop_name=rop_name, hip=os.path.basename(hip_file))

  def remove_rop_from_queue(self):
      selected_rows = self.queue_table.selectedIndexes()
      if not selected_rows:
          self.log_t("select_queue_row")
          return
      row = selected_rows[0].row()
      self.queue_table.removeRow(row)
      self.update_start_button()
      self.save_state()
      self.log_t("rop_removed")

  def on_queue_cell_changed(self, row, col):
      """Handle changes to queue table cells"""
      if self._queue_cell_edit_guard or self._resize_update_guard:
          return

      if col in (COL_HIP, COL_OUTPUT):
          return

      if col == 9:
          try:
              base_x, base_y, resize_pct, actual_x, actual_y = self._apply_resize_display(row)
              self.log_t(
                  "resize_changed",
                  row=row + 1,
                  base_x=base_x,
                  base_y=base_y,
                  actual_x=actual_x,
                  actual_y=actual_y,
                  resize_pct=resize_pct,
              )
          except Exception as e:
              self.log_t("resize_error", e=e)

      if col in (7, 8):
          try:
              base_x, base_y, _, actual_x, actual_y = self.queue_model.resolve_render_size(row)
              self.log_t(
                  "size_changed",
                  row=row + 1,
                  base_x=base_x,
                  base_y=base_y,
                  actual_x=actual_x,
                  actual_y=actual_y,
              )
          except Exception as e:
              self.log_t("size_error", e=e)

      if col not in (0, 6, COL_SEND_MP4):
          self.save_state()

  def _on_queue_double_clicked(self, index):
      if not index.isValid():
          return
      self.on_queue_cell_double_clicked(index.row(), index.column())

  def on_queue_cell_double_clicked(self, row, col):
      if col not in (COL_OUTPUT, COL_HIP):
          return
      full = self.queue_model.get_path(row, col)
      if not full:
          return
      self.queue_table.edit(self.queue_model.index(row, col))

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

  def log_t(self, key, **kwargs):
      self.log(log_msg(self.current_language, key, **kwargs))

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
          self.log_t("no_hip_selected")
          return

      self.last_scanned_hip = hip_file
      self.update_hip_scan_label()
      
      try:
          rops_data, error = self._run_scan(hip_file)
          if error:
              self.log(f"❌ {error}")
              return
          
          self.all_rops = rops_data
          
          self.log_t("scan_found", count=len(self.all_rops), hip=os.path.basename(hip_file))
          self.update_rop_list()
          self.update_rop_count_label()
          self.add_queue_btn.setEnabled(True)
          set_next_style(self.add_queue_btn)
          self.add_all_rops_btn.setEnabled(True)
          set_next_style(self.add_all_rops_btn)
      except Exception as e:
          self.log_t("scan_fail", e=e)

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