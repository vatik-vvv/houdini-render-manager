"""Render queue: QAbstractTableModel + QTableView (stable reorder and roles)."""
from __future__ import annotations

import copy

from path_utils import path_tooltip
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal, QItemSelectionModel, QSize
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QAbstractItemView, QApplication, QTableView, QSizePolicy

from ui_theme import STATUS_STYLES, TOGGLE_OFF_COLOR, TOGGLE_ON_COLOR

QUEUE_COLUMN_KEYS = [
    "enabled", "hip", "rop", "type", "start_frame", "end_frame", "skip",
    "size_x", "size_y", "resize", "output_path", "status", "send2bot", "send_mp4",
    "start_time", "end_time", "duration", "eta",
]
COL_HIP, COL_ROP, COL_OUTPUT, COL_STATUS = 1, 2, 10, 11
COL_SEND2BOT, COL_SEND_MP4 = 12, 13
COL_START_TIME, COL_END_TIME, COL_DURATION, COL_ETA = 14, 15, 16, 17
TOGGLE_COLUMNS = {0, 6, COL_SEND_MP4}
EDITABLE_TEXT_COLUMNS = {4, 5, 9, 10, COL_SEND2BOT}

FULL_PATH_ROLE = Qt.ItemDataRole.UserRole
RENDER_PROGRESS_ROLE = Qt.ItemDataRole.UserRole + 2
BASE_SIZE_X_ROLE = Qt.ItemDataRole.UserRole + 3
BASE_SIZE_Y_ROLE = Qt.ItemDataRole.UserRole + 4


def normalize_toggle_value(raw_val, default="0"):
    if raw_val is None or raw_val == "":
        return default
    s = str(raw_val).lower()
    return "1" if s in ("true", "1", "yes") else "0"


def is_toggle_checked_value(raw_val):
    return normalize_toggle_value(raw_val, "0") == "1"


def _path_display(full_path):
    if not full_path:
        return ""
    norm = full_path.replace("\\", "/")
    parts = [p for p in norm.split("/") if p]
    if len(norm) > 52 and len(parts) > 2:
        return "…/" + "/".join(parts[-3:])
    return full_path


def _parse_resize_pct(resize_text):
    if not resize_text:
        return 100.0
    text = str(resize_text).strip().rstrip("%")
    try:
        return float(text) if text else 100.0
    except ValueError:
        return 100.0


def _empty_row():
    return {
        "enabled": "1",
        "hip": "",
        "rop": "",
        "type": "",
        "start_frame": "1",
        "end_frame": "100",
        "skip": "0",
        "size_x": "1920",
        "size_y": "1080",
        "resize": "100%",
        "output_path": "",
        "status": "Queued",
        "send2bot": "0",
        "send_mp4": "0",
        "start_time": "",
        "end_time": "",
        "duration": "--",
        "size_x_base": "1920",
        "size_y_base": "1080",
        "_progress": None,
        "_work_done": None,
        "_work_total": None,
        "_scene_frame": None,
        "_eta_display": "--",
        "_eta_tooltip": "",
    }


class RenderQueueModel(QAbstractTableModel):
    data_changed_user = Signal(int, int)

    def __init__(self, headers=None, parent=None):
        super().__init__(parent)
        self._headers = headers or []
        self._rows: list[dict] = []

    def set_headers(self, headers):
        self._headers = list(headers)
        if self._headers:
            self.headerDataChanged.emit(
                Qt.Orientation.Horizontal, 0, len(self._headers) - 1
            )

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(QUEUE_COLUMN_KEYS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        if 0 <= section < len(self._headers):
            return self._headers[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        col = index.column()
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if col in TOGGLE_COLUMNS:
            return base
        if col in EDITABLE_TEXT_COLUMNS:
            return base | Qt.ItemFlag.ItemIsEditable
        if col in (7, 8):
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def _row(self, row):
        return self._rows[row]

    def _toggle_bg(self, checked):
        return QBrush(TOGGLE_ON_COLOR if checked else TOGGLE_OFF_COLOR)

    def _status_bg_fg(self, status):
        colors = STATUS_STYLES.get(status or "Queued")
        if colors:
            return QBrush(colors[0]), QBrush(colors[1])
        return QBrush(QColor(70, 70, 70)), QBrush(QColor(220, 220, 220))

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if row < 0 or row >= len(self._rows):
            return None
        entry = self._rows[row]
        key = QUEUE_COLUMN_KEYS[col]

        if role == RENDER_PROGRESS_ROLE:
            return entry.get("_progress")

        if col in TOGGLE_COLUMNS:
            checked = is_toggle_checked_value(entry.get(key))
            if role == Qt.ItemDataRole.DisplayRole:
                return ""
            if role == Qt.ItemDataRole.CheckStateRole:
                return Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            if role == Qt.ItemDataRole.UserRole:
                return "1" if checked else "0"
            if role == Qt.ItemDataRole.BackgroundRole:
                return self._toggle_bg(checked)
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(Qt.AlignmentFlag.AlignCenter)
            return None

        if col == COL_HIP:
            full = entry.get("hip", "")
            if role == FULL_PATH_ROLE:
                return full
            if role == Qt.ItemDataRole.DisplayRole:
                return _path_display(full)
            if role == Qt.ItemDataRole.ToolTipRole and full:
                return full
            return None

        if col == COL_OUTPUT:
            full = entry.get("output_path", "")
            if role == FULL_PATH_ROLE:
                return full
            if role == Qt.ItemDataRole.DisplayRole:
                return _path_display(full)
            if role == Qt.ItemDataRole.ToolTipRole:
                tip = path_tooltip(full, entry.get("hip"), entry.get("rop"))
                return tip or full
            return None

        if col in (7, 8):
            base_x = int(float(entry.get("size_x_base", entry.get("size_x", 1920))))
            base_y = int(float(entry.get("size_y_base", entry.get("size_y", 1080))))
            pct = _parse_resize_pct(entry.get("resize", "100%"))
            actual_x = max(1, int(base_x * pct / 100))
            actual_y = max(1, int(base_y * pct / 100))
            if role == Qt.ItemDataRole.DisplayRole:
                return str(actual_x if col == 7 else actual_y)
            if role == BASE_SIZE_X_ROLE and col == 7:
                return str(base_x)
            if role == BASE_SIZE_Y_ROLE and col == 8:
                return str(base_y)
            return None

        if col == COL_STATUS:
            status = entry.get("status", "Queued")
            if isinstance(status, str) and status.startswith("Running "):
                status = "Running"
            if role == Qt.ItemDataRole.DisplayRole:
                if status == "Running":
                    total = entry.get("_work_total")
                    if total is not None:
                        try:
                            work_total = int(total)
                            work_done = int(entry.get("_work_done") or 0)
                            progress = f"{work_done}/{work_total}"
                            scene_frame = entry.get("_scene_frame")
                            if scene_frame is not None:
                                return f"{int(scene_frame)} ({progress})"
                            return f"Running {progress}"
                        except (TypeError, ValueError):
                            pass
                return status
            if role == Qt.ItemDataRole.BackgroundRole:
                return self._status_bg_fg(status)[0]
            if role == Qt.ItemDataRole.ForegroundRole:
                return self._status_bg_fg(status)[1]
            return None

        if col == COL_ETA:
            if role == Qt.ItemDataRole.DisplayRole:
                return entry.get("_eta_display", "--")
            if role == Qt.ItemDataRole.ToolTipRole:
                tip = entry.get("_eta_tooltip", "")
                return tip or None
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            return str(entry.get(key, "") or "")

        if role == Qt.ItemDataRole.BackgroundRole and col == COL_STATUS:
            return self._status_bg_fg(entry.get("status", "Queued"))[0]
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid():
            return False
        row, col = index.row(), index.column()
        entry = self._rows[row]
        key = QUEUE_COLUMN_KEYS[col]

        if col in TOGGLE_COLUMNS and role in (
            Qt.ItemDataRole.UserRole,
            Qt.ItemDataRole.CheckStateRole,
        ):
            checked = value == Qt.CheckState.Checked if role == Qt.ItemDataRole.CheckStateRole else normalize_toggle_value(value) == "1"
            entry[key] = "1" if checked else "0"
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.UserRole])
            self.data_changed_user.emit(row, col)
            return True

        if role == RENDER_PROGRESS_ROLE:
            entry["_progress"] = value
            self.dataChanged.emit(index, index, [RENDER_PROGRESS_ROLE, Qt.ItemDataRole.DisplayRole])
            return True

        if col == COL_HIP and role == FULL_PATH_ROLE:
            entry["hip"] = str(value or "").strip()
            self.dataChanged.emit(index, index)
            self.data_changed_user.emit(row, col)
            return True

        if col == COL_OUTPUT and role == FULL_PATH_ROLE:
            entry["output_path"] = str(value or "").strip()
            self.dataChanged.emit(index, index)
            self.data_changed_user.emit(row, col)
            return True

        if role == Qt.ItemDataRole.EditRole:
            if col == 9:
                self.set_resize(row, str(value))
                self.data_changed_user.emit(row, col)
                return True
            if col in (7, 8):
                try:
                    val = max(1, int(float(value)))
                except (TypeError, ValueError):
                    return False
                bx, by = self.read_base_resolution(row)
                if bx is None:
                    bx, by = 1920, 1080
                if col == 7:
                    bx = val
                else:
                    by = val
                self.set_resize(row, "100%", base_x=bx, base_y=by)
                self.data_changed_user.emit(row, col)
                return True
            entry[key] = str(value)
            if col == COL_STATUS:
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ForegroundRole])
            else:
                self.dataChanged.emit(index, index)
            self.data_changed_user.emit(row, col)
            return True
        return False

    def load_entries(self, entries):
        self.beginResetModel()
        self._rows = [self._normalize_entry(e) for e in entries]
        self.endResetModel()

    def all_entries(self):
        return [self.row_to_entry(r) for r in range(self.rowCount())]

    def _normalize_entry(self, entry):
        row = _empty_row()
        row.update({k: v for k, v in (entry or {}).items() if k in row or k in ("size_x_base", "size_y_base")})
        row["enabled"] = normalize_toggle_value(row.get("enabled"), "1")
        row["skip"] = normalize_toggle_value(row.get("skip"), "0")
        row["send_mp4"] = normalize_toggle_value(row.get("send_mp4"), "0")
        if not str(row.get("resize", "")).strip().endswith("%"):
            row["resize"] = f"{_parse_resize_pct(row.get('resize')):g}%"
        bx = row.get("size_x_base") or row.get("size_x") or "1920"
        by = row.get("size_y_base") or row.get("size_y") or "1080"
        row["size_x_base"] = str(bx)
        row["size_y_base"] = str(by)
        row["_progress"] = None
        row["_eta_display"] = "--"
        row["_eta_tooltip"] = ""
        return row

    def row_to_entry(self, row):
        entry = copy.deepcopy(self._rows[row])
        entry.pop("_progress", None)
        entry.pop("_eta_display", None)
        entry.pop("_eta_tooltip", None)
        pct = _parse_resize_pct(entry.get("resize", "100%"))
        base_x = max(1, int(float(entry.get("size_x_base", 1920))))
        base_y = max(1, int(float(entry.get("size_y_base", 1080))))
        entry["size_x"] = str(max(1, int(base_x * pct / 100)))
        entry["size_y"] = str(max(1, int(base_y * pct / 100)))
        return entry

    def insert_entry(self, row, entry):
        self.beginInsertRows(QModelIndex(), row, row)
        self._rows.insert(row, self._normalize_entry(entry))
        self.endInsertRows()

    def remove_rows(self, row, count=1):
        if count <= 0:
            return
        self.beginRemoveRows(QModelIndex(), row, row + count - 1)
        del self._rows[row : row + count]
        self.endRemoveRows()

    def move_row(self, src_row, dest_row):
        count = self.rowCount()
        if src_row < 0 or src_row >= count:
            return False
        dest_row = max(0, min(int(dest_row), count))
        if src_row == dest_row or src_row + 1 == dest_row:
            return False
        entry = self._rows.pop(src_row)
        if dest_row > src_row:
            dest_row -= 1
        self._rows.insert(dest_row, entry)
        self.beginResetModel()
        self.endResetModel()
        return True

    def clear_render_progress(self, row):
        if row < 0 or row >= len(self._rows):
            return
        self._rows[row]["_progress"] = None
        self._rows[row]["_scene_frame"] = None
        idx = self.index(row, COL_STATUS)
        self.dataChanged.emit(idx, idx, [RENDER_PROGRESS_ROLE, Qt.ItemDataRole.DisplayRole])

    def set_status(self, row, status, progress=None, work_done=None, work_total=None, scene_frame=None):
        if row < 0 or row >= len(self._rows):
            return
        if isinstance(status, str) and status.startswith("Running "):
            status = "Running"
        self._rows[row]["status"] = status
        if progress is not None:
            self._rows[row]["_progress"] = progress
        if work_done is not None:
            self._rows[row]["_work_done"] = work_done
        if work_total is not None:
            self._rows[row]["_work_total"] = work_total
        if scene_frame is not None:
            try:
                self._rows[row]["_scene_frame"] = int(scene_frame) if int(scene_frame) >= 0 else None
            except (TypeError, ValueError):
                pass
        if status != "Running":
            self._rows[row]["_progress"] = None
            self._rows[row]["_work_done"] = None
            self._rows[row]["_work_total"] = None
            self._rows[row]["_scene_frame"] = None
        idx = self.index(row, COL_STATUS)
        self.dataChanged.emit(
            idx,
            idx,
            [
                RENDER_PROGRESS_ROLE,
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.BackgroundRole,
                Qt.ItemDataRole.ForegroundRole,
            ],
        )

    def set_times(self, row, start_time=None, end_time=None, duration=None):
        if row < 0 or row >= len(self._rows):
            return
        if start_time is not None:
            self._rows[row]["start_time"] = start_time
        if end_time is not None:
            self._rows[row]["end_time"] = end_time
        if duration is not None:
            self._rows[row]["duration"] = duration
        for col in (COL_START_TIME, COL_END_TIME, COL_DURATION):
            self.dataChanged.emit(self.index(row, col), self.index(row, col))

    def set_eta_display(self, row, text, tooltip=""):
        if row < 0 or row >= len(self._rows):
            return
        self._rows[row]["_eta_display"] = text
        self._rows[row]["_eta_tooltip"] = tooltip or ""
        idx = self.index(row, COL_ETA)
        self.dataChanged.emit(
            idx,
            idx,
            [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole],
        )

    def set_path(self, row, col, path, hip_file=None, op_name=None):
        key = "hip" if col == COL_HIP else "output_path"
        self._rows[row][key] = (path or "").strip()
        if col == COL_OUTPUT and hip_file is not None:
            self._rows[row]["hip"] = self._rows[row].get("hip") or hip_file
        if col == COL_OUTPUT and op_name is not None:
            self._rows[row]["rop"] = self._rows[row].get("rop") or op_name
        self.dataChanged.emit(self.index(row, col), self.index(row, col))

    def get_path(self, row, col):
        key = "hip" if col == COL_HIP else "output_path"
        return str(self._rows[row].get(key, "") or "").strip()

    def get_text(self, row, col):
        idx = self.index(row, col)
        val = self.data(idx, Qt.ItemDataRole.DisplayRole)
        return "" if val is None else str(val)

    def set_resize(self, row, resize_text, base_x=None, base_y=None):
        entry = self._rows[row]
        if base_x is not None:
            entry["size_x_base"] = str(int(base_x))
        if base_y is not None:
            entry["size_y_base"] = str(int(base_y))
        text = str(resize_text).strip()
        if text and not text.endswith("%"):
            text = f"{_parse_resize_pct(text):g}%"
        entry["resize"] = text
        for col in (7, 8, 9):
            self.dataChanged.emit(self.index(row, col), self.index(row, col))

    def read_base_resolution(self, row):
        try:
            return (
                int(float(self._rows[row].get("size_x_base", 1920))),
                int(float(self._rows[row].get("size_y_base", 1080))),
            )
        except (TypeError, ValueError):
            return None, None

    def resolve_render_size(self, row):
        entry = self._rows[row]
        pct = _parse_resize_pct(entry.get("resize", "100%"))
        base_x, base_y = self.read_base_resolution(row)
        if base_x is None:
            base_x, base_y = 1920, 1080
        actual_x = max(1, int(base_x * pct / 100))
        actual_y = max(1, int(base_y * pct / 100))
        return base_x, base_y, pct, actual_x, actual_y


    def set_enabled(self, row, enabled):
        if row < 0 or row >= len(self._rows):
            return
        self._rows[row]["enabled"] = "1" if enabled else "0"
        self.dataChanged.emit(self.index(row, 0), self.index(row, 0))

    def set_field(self, row, key, value):
        if row < 0 or row >= len(self._rows) or key not in _empty_row():
            return
        self._rows[row][key] = value
        if key in QUEUE_COLUMN_KEYS:
            col = QUEUE_COLUMN_KEYS.index(key)
            self.dataChanged.emit(self.index(row, col), self.index(row, col))

    def reset_status_row(self, row):
        if row < 0 or row >= len(self._rows):
            return
        entry = self._rows[row]
        entry["status"] = "Queued"
        entry["_progress"] = None
        entry["_work_done"] = None
        entry["_work_total"] = None
        entry["_scene_frame"] = None
        entry["start_time"] = ""
        entry["end_time"] = ""
        entry["duration"] = "--"
        entry["_eta_display"] = "--"
        entry["_eta_tooltip"] = ""
        for col in (COL_STATUS, COL_START_TIME, COL_END_TIME, COL_DURATION, COL_ETA):
            self.dataChanged.emit(self.index(row, col), self.index(row, col))


class QueueCellProxy:
    """Adapter so queue code can call .text() / .data() on model cells."""

    def __init__(self, model: RenderQueueModel, row: int, col: int):
        self._model = model
        self._row = row
        self._col = col
        self._index = model.index(row, col)

    def text(self):
        return self._model.get_text(self._row, self._col)

    def setText(self, value):
        self._model.setData(self._index, value, Qt.ItemDataRole.EditRole)

    def data(self, role):
        return self._model.data(self._index, role)

    def setData(self, role, value):
        return self._model.setData(self._index, value, role)


def model_item(model, row, col):
    if model is None or row < 0 or row >= model.rowCount() or col < 0:
        return None
    return QueueCellProxy(model, row, col)


class RenderQueueView(QTableView):
    """Drag row reorder via model.move_row — no Qt InternalMove."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(28)
        self.setMouseTracking(True)
        self._press_row = -1
        self._press_pos = None
        self._dragging = False
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def minimumSizeHint(self):
        """Do not force window size from column widths or row count."""
        hh = self.horizontalHeader().height() if self.horizontalHeader() else 24
        rh = self.rowHeight(0) if self.rowCount() > 0 else 24
        return QSize(0, hh + rh * 2)

    def queue_model(self) -> RenderQueueModel:
        return self.model()

    def item(self, row, col):
        return model_item(self.model(), row, col)

    def rowCount(self):
        m = self.model()
        return m.rowCount() if m else 0

    def removeRow(self, row):
        m = self.model()
        if m:
            m.remove_rows(row, 1)

    def selectRow(self, row):
        m = self.model()
        if m and 0 <= row < m.rowCount():
            idx = m.index(row, 0)
            self.selectionModel().select(
                idx,
                QItemSelectionModel.SelectionFlag.ClearAndSelect
                | QItemSelectionModel.SelectionFlag.Rows,
            )

    def scrollToItem(self, proxy, hint=None):
        if proxy and hasattr(proxy, "_index"):
            self.scrollTo(proxy._index)

    def setHorizontalHeaderLabels(self, labels):
        m = self.model()
        if m and hasattr(m, "set_headers"):
            m.set_headers(labels)

    def columnCount(self):
        m = self.model()
        return m.columnCount() if m else 0

    def _insert_index_at(self, pos):
        idx = self.indexAt(pos)
        if not idx.isValid():
            return self.model().rowCount()
        row = idx.row()
        if pos.y() > self.visualRect(idx).center().y():
            row += 1
        return max(0, min(row, self.model().rowCount()))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.indexAt(event.pos())
            if index.isValid():
                self._press_row = index.row()
                self._press_pos = event.pos()
                self._dragging = False
            else:
                self._press_row = -1
                self.clearSelection()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._press_row >= 0
            and event.buttons() & Qt.MouseButton.LeftButton
            and self._press_pos is not None
        ):
            if not self._dragging:
                if (event.pos() - self._press_pos).manhattanLength() >= QApplication.startDragDistance():
                    self._dragging = True
                    self.selectRow(self._press_row)
            if self._dragging:
                self.viewport().setCursor(Qt.CursorShape.DragMoveCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._dragging
            and self._press_row >= 0
            and self.parent_window
            and hasattr(self.parent_window, "_move_queue_row")
        ):
            dest = self._insert_index_at(event.pos())
            self.parent_window._move_queue_row(self._press_row, dest)
        self._press_row = -1
        self._press_pos = None
        self._dragging = False
        self.viewport().unsetCursor()
        super().mouseReleaseEvent(event)
