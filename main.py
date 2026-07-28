import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional



import serial
from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPalette, QTextCharFormat, QTextCursor, QTextDocument

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)



from serial.tools import list_ports


BAUD_RATES = ["1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]
DATA_BITS = {
    "5": serial.FIVEBITS,
    "6": serial.SIXBITS,
    "7": serial.SEVENBITS,
    "8": serial.EIGHTBITS,
}
STOP_BITS = {
    "1": serial.STOPBITS_ONE,
    "1.5": serial.STOPBITS_ONE_POINT_FIVE,
    "2": serial.STOPBITS_TWO,
}
PARITY = {
    "None": serial.PARITY_NONE,
    "Odd": serial.PARITY_ODD,
    "Even": serial.PARITY_EVEN,
}

RECEIVE_LIMIT_OPTIONS = {
    "512KB": 512 * 1024,
    "1MB": 1 * 1024 * 1024,
    "10MB": 10 * 1024 * 1024,
    "40MB": 40 * 1024 * 1024,
}

COMMANDS_STORE_PATH = os.path.join(os.path.expanduser("~"), ".serial_assistant_commands.json")
DEFAULT_COMMAND_LINES = [
    "AT^GT_CM=PCBA,ID,CPU",
    "AT^GT_CM=PCBA,VERSION",
    "AT^GT_CM=PCBA,SIM",
    "AT^GT_CM=PCBA,WIFI,ON",
    "AT^GT_CM=PCBA,RF_BAR",
    "AT^GT_CM=PCBA,SERVER",
    "AT^GT_CM=PCBA,MCU,VERSION",
    "AT^GT_CM=PCBA,TEST",
    "AT^GT_CM=PCBA,MCU,CHARGE_IC,0",
    "AT^GT_CM=PCBA,MCU,VOLT",
    "AT^GT_CM=PCBA,MCU,NTC",
    "AT^GT_CM=PCBA,BMT",
    "AT^GT_CM=PCBA,MCU,CHARGE_IC,2",
    "AT^GT_CM=PCBA,MCU,VOLT",
    "AT^GT_CM=PCBA,MCU,LIGHT",
    "AT^GT_CM=PCBA,MCU,KEY",
    "AT^GT_CM=PCBA,MCU,KEY",
    "AT^GT_CM=PCBA,MCU,LED,ON",
    "AT^GT_CM=PCBA,MCU,LED,OFF",
    "AT^GT_CM=PCBA,BATLED,GREEN",
    "AT^GT_CM=PCBA,BATLED,YELLOW",
    "AT^GT_CM=PCBA,BATLED,RED",
    "AT^GT_CM=PCBA,BATLED,OFF",
    "AT^GT_CM=PCBA,NETLED,ON",
    "AT^GT_CM=PCBA,NETLED,OFF",
    "AT^GT_CM=PCBA,WIFI,SCAN",
    "AT^GT_CM=PCBA,WIFI,OFF",
    "AT^GT_CM=PCBA,MCU,MAC",
    "AT^GT_CM=PCBA,MCU,TEMP",
    "AT^GT_CM=PCBA,IMSI",
    "AT^GT_CM=PCBA,CSQ_4G",
    "AT^GT_CM=PCBA,MCU,SHUTDOWN",
]


def resource_path(relative_path: str) -> str:



    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)


@dataclass
class SerialConfig:

    port: str
    baud_rate: int
    data_bits: int
    stop_bits_key: str
    parity: str


class SerialReadThread(QThread):
    data_received = Signal(bytes)
    error_occurred = Signal(str)

    def __init__(self, serial_port: serial.Serial):
        super().__init__()
        self.serial_port = serial_port
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        while self._running:
            try:
                waiting = self.serial_port.in_waiting
                if waiting > 0:
                    data = self.serial_port.read(waiting)
                    if data:
                        self.data_received.emit(data)
                else:
                    self.msleep(20)
            except Exception as e:
                self.error_occurred.emit(str(e))
                break


def _set_opaque_background(widget: QWidget, color: str) -> None:
    """强制 QWidget 不透明填充背景。

    普通 QWidget 叠加 QGraphicsEffect(如投影) 时不会自动填充背景，
    会整块变透明。这里同时开启 WA_StyledBackground 并用调色板兜底。
    """
    widget.setAttribute(Qt.WA_StyledBackground, True)
    widget.setAutoFillBackground(True)
    palette = widget.palette()
    palette.setColor(QPalette.Window, QColor(color))
    widget.setPalette(palette)


class _CommandPanelTitleBar(QWidget):
    """悬浮命令面板的标题栏，负责拖动与关闭按钮。"""

    def __init__(self, panel: "FloatingCommandPanel") -> None:
        super().__init__(panel)
        self._panel = panel
        self._drag_offset = None
        self.setFixedHeight(30)
        self.setObjectName("commandPanelTitleBar")
        _set_opaque_background(self, "#BF360C")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(6)

        self.title_label = QLabel("命令表")
        self.title_label.setStyleSheet("font-weight:600;")

        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("commandPanelCloseButton")
        self.close_button.setFixedSize(22, 22)

        layout.addWidget(self.title_label)
        layout.addStretch(1)
        layout.addWidget(self.close_button)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            parent = self._panel.parentWidget()
            global_top = parent.mapToGlobal(self._panel.pos())
            self._drag_offset = event.globalPosition().toPoint() - global_top
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and (event.buttons() & Qt.LeftButton):
            global_pos = event.globalPosition().toPoint()
            parent = self._panel.parentWidget()
            local_pos = parent.mapFromGlobal(global_pos - self._drag_offset)
            self._panel.move(local_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class FloatingCommandPanel(QWidget):
    """不进入主布局的悬浮命令面板，叠加显示，可拖动、可关闭。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("floatingCommandPanel")
        _set_opaque_background(self, "#FFFFFF")
        self.setMinimumWidth(360)
        self.setMinimumHeight(240)
        self.resize(440, 380)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        self.title_bar = _CommandPanelTitleBar(self)
        self.body = QWidget()
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(8, 6, 8, 8)
        body_layout.setSpacing(6)

        outer.addWidget(self.title_bar)
        outer.addWidget(self.body, 1)

        self._body_layout = body_layout
        self.close_button = self.title_bar.close_button

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 70))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        self.setStyleSheet(
            "#floatingCommandPanel {"
            "  background: #FFFFFF; border: 2px solid #E65100; border-radius: 8px;"
            "}"
            "#commandPanelTitleBar {"
            "  background: #BF360C; border-top-left-radius: 6px; border-top-right-radius: 6px;"
            "}"
            "#commandPanelTitleBar QLabel { border: none; background: transparent; color: #FFFFFF; font-weight: 700; }"
            "#commandPanelCloseButton {"
            "  border: none; background: transparent; font-weight: 700; color: #FFFFFF;"
            "}"
            "#commandPanelCloseButton:hover {"
            "  background: #7F1D1D; color: #FFFFFF; border-radius: 4px;"
            "}"
        )

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout


class SerialTab(QWidget):
    status_changed = Signal(str)

    def __init__(self, tab_name: str):
        super().__init__()
        self.tab_name = tab_name
        self.serial_port: Optional[serial.Serial] = None
        self.reader_thread: Optional[SerialReadThread] = None
        self.rx_count = 0
        self.tx_count = 0
        self._displayed_text_bytes = 0
        self._txt_log_write_error_notified = False
        self._commands_write_error_notified = False
        self._build_ui()

        self.refresh_ports()
        self._load_command_presets()


    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        top_layout = QGridLayout()

        self.port_combo = QComboBox()

        self.baud_combo = QComboBox()
        self.baud_combo.setEditable(True)
        self.baud_combo.addItems(BAUD_RATES)
        self.baud_combo.setCurrentText("115200")

        self.data_bits_combo = QComboBox()
        self.data_bits_combo.addItems(DATA_BITS.keys())
        self.data_bits_combo.setCurrentText("8")

        self.stop_bits_combo = QComboBox()
        self.stop_bits_combo.addItems(STOP_BITS.keys())
        self.stop_bits_combo.setCurrentText("1")

        self.parity_combo = QComboBox()
        self.parity_combo.addItems(PARITY.keys())
        self.parity_combo.setCurrentText("None")

        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(["gbk", "gb18030", "utf-8"])
        self.encoding_combo.setCurrentText("gbk")

        self.refresh_button = QPushButton("刷新串口")
        self.open_button = QPushButton("打开串口")

        top_layout.addWidget(QLabel("串口"), 0, 0)
        top_layout.addWidget(self.port_combo, 0, 1)
        top_layout.addWidget(self.refresh_button, 0, 2)
        top_layout.addWidget(QLabel("波特率"), 0, 3)
        top_layout.addWidget(self.baud_combo, 0, 4)

        top_layout.addWidget(QLabel("数据位"), 1, 0)
        top_layout.addWidget(self.data_bits_combo, 1, 1)
        top_layout.addWidget(QLabel("停止位"), 1, 2)
        top_layout.addWidget(self.stop_bits_combo, 1, 3)
        top_layout.addWidget(QLabel("校验位"), 1, 4)
        top_layout.addWidget(self.parity_combo, 1, 5)

        top_layout.addWidget(QLabel("编码"), 0, 5)
        top_layout.addWidget(self.encoding_combo, 0, 6)
        top_layout.addWidget(self.open_button, 1, 6)

        self.receive_area = QPlainTextEdit()
        self.receive_area.setReadOnly(True)
        self.receive_area.setPlaceholderText("接收数据显示区域")
        self.receive_area.setStyleSheet(
            "QPlainTextEdit { selection-background-color: #FFB300; selection-color: #1A1A1A; }"
        )


        search_top_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索关键字")
        self.search_prev_button = QPushButton("上一个")
        self.search_next_button = QPushButton("下一个")

        search_top_layout.addWidget(QLabel("搜索"))
        search_top_layout.addWidget(self.search_input, 1)
        search_top_layout.addWidget(self.search_prev_button)
        search_top_layout.addWidget(self.search_next_button)

        search_bottom_layout = QHBoxLayout()
        self.highlight_button = QPushButton("高亮全部")
        self.clear_highlight_button = QPushButton("清除高亮")
        search_bottom_layout.addWidget(self.highlight_button)
        search_bottom_layout.addWidget(self.clear_highlight_button)
        search_bottom_layout.addStretch(1)

        send_input_layout = QHBoxLayout()
        self.send_input = QLineEdit()
        self.send_input.setPlaceholderText("输入要发送的数据")
        self.send_button = QPushButton("发送")
        send_input_layout.addWidget(self.send_input, 1)
        send_input_layout.addWidget(self.send_button)

        self.toggle_command_panel_button = QPushButton("命令表 ▶")
        self.toggle_command_panel_button.setCheckable(True)
        self.toggle_command_panel_button.setChecked(False)

        command_top_layout = QHBoxLayout()
        self.command_name_input = QLineEdit()
        self.command_name_input.setPlaceholderText("命令名称(可选)")
        self.command_value_input = QLineEdit()
        self.command_value_input.setPlaceholderText("命令内容")
        self.add_command_button = QPushButton("加入命令表")
        self.import_command_button = QPushButton("导入")
        self.remove_command_button = QPushButton("删除选中")
        self.send_command_button = QPushButton("发送选中")

        command_top_layout.addWidget(QLabel("命令表"))
        command_top_layout.addWidget(self.command_name_input)
        command_top_layout.addWidget(self.command_value_input, 1)
        command_top_layout.addWidget(self.add_command_button)
        command_top_layout.addWidget(self.import_command_button)
        command_top_layout.addWidget(self.remove_command_button)
        command_top_layout.addWidget(self.send_command_button)


        self.command_table = QTableWidget(0, 2)

        self.command_table.setHorizontalHeaderLabels(["名称", "命令内容"])
        header = self.command_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.command_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.command_table.setSelectionMode(QTableWidget.SingleSelection)
        self.command_table.setAlternatingRowColors(True)

        self.command_panel = FloatingCommandPanel(self)
        self.command_panel.body_layout().addLayout(command_top_layout)
        self.command_panel.body_layout().addWidget(self.command_table, 1)
        self.command_panel.setVisible(False)
        self.command_panel.close_button.clicked.connect(
            lambda: self.toggle_command_panel_button.setChecked(False)
        )
        self._command_panel_placed = False

        control_top_layout = QHBoxLayout()


        self.hex_mode_checkbox = QCheckBox("HEX收发")
        self.add_newline_checkbox = QCheckBox("发送附加\\r\\n")
        self.timestamp_checkbox = QCheckBox("显示时间戳")
        self.timestamp_checkbox.setChecked(True)
        self.auto_scroll_checkbox = QCheckBox("自动滚动(接收)")
        self.auto_scroll_checkbox.setChecked(True)

        control_top_layout.addWidget(self.hex_mode_checkbox)
        control_top_layout.addWidget(self.add_newline_checkbox)
        control_top_layout.addWidget(self.timestamp_checkbox)
        control_top_layout.addWidget(self.auto_scroll_checkbox)
        control_top_layout.addStretch(1)

        control_bottom_layout = QHBoxLayout()
        self.loop_send_checkbox = QCheckBox("定时发送")
        self.loop_interval_spin = QSpinBox()
        self.loop_interval_spin.setRange(10, 60000)
        self.loop_interval_spin.setValue(1000)
        self.loop_interval_spin.setSuffix(" ms")

        self.receive_limit_combo = QComboBox()
        for label, size in RECEIVE_LIMIT_OPTIONS.items():
            self.receive_limit_combo.addItem(label, size)
        self.receive_limit_combo.setCurrentText("10MB")

        self.clear_button = QPushButton("清空接收区")

        control_bottom_layout.addWidget(self.loop_send_checkbox)
        control_bottom_layout.addWidget(self.loop_interval_spin)
        control_bottom_layout.addSpacing(8)
        control_bottom_layout.addWidget(QLabel("接收上限"))
        control_bottom_layout.addWidget(self.receive_limit_combo)
        control_bottom_layout.addSpacing(8)
        control_bottom_layout.addWidget(self.clear_button)
        control_bottom_layout.addStretch(1)

        log_file_layout = QHBoxLayout()
        self.log_to_file_checkbox = QCheckBox("实时写入TXT")
        self.log_file_path_input = QLineEdit()
        self.log_file_path_input.setPlaceholderText("选择TXT文件路径")
        self.select_log_file_button = QPushButton("选择文件")

        log_file_layout.addWidget(self.log_to_file_checkbox)
        log_file_layout.addWidget(self.log_file_path_input, 1)
        log_file_layout.addWidget(self.select_log_file_button)

        self.stats_label = QLabel("RX: 0 bytes | TX: 0 bytes | 未连接")

        root_layout.addLayout(top_layout)
        root_layout.addWidget(self.receive_area, 1)
        root_layout.addLayout(search_top_layout)
        root_layout.addLayout(search_bottom_layout)
        root_layout.addLayout(send_input_layout)
        root_layout.addWidget(self.toggle_command_panel_button)
        root_layout.addLayout(control_top_layout)


        root_layout.addLayout(control_bottom_layout)
        root_layout.addLayout(log_file_layout)
        root_layout.addWidget(self.stats_label)





        self.loop_timer = QTimer(self)

        self.refresh_button.clicked.connect(self.refresh_ports)
        self.open_button.clicked.connect(self.toggle_connection)
        self.send_button.clicked.connect(self.send_data)
        self.clear_button.clicked.connect(self.clear_receive_area)
        self.loop_send_checkbox.stateChanged.connect(self._on_loop_send_changed)
        self.loop_timer.timeout.connect(self.send_data)

        self.search_prev_button.clicked.connect(lambda: self.find_text(forward=False))
        self.search_next_button.clicked.connect(lambda: self.find_text(forward=True))
        self.search_input.returnPressed.connect(lambda: self.find_text(forward=True))
        self.highlight_button.clicked.connect(self.highlight_all_matches)
        self.clear_highlight_button.clicked.connect(self.clear_highlight)
        self.receive_limit_combo.currentIndexChanged.connect(self._trim_receive_area_to_limit)
        self.select_log_file_button.clicked.connect(self.select_log_file)
        self.log_to_file_checkbox.stateChanged.connect(self._on_log_to_file_changed)
        self.toggle_command_panel_button.toggled.connect(self._toggle_command_panel)
        self.add_command_button.clicked.connect(self.add_command_preset)
        self.import_command_button.clicked.connect(self.import_command_presets)
        self.remove_command_button.clicked.connect(self.remove_selected_command_preset)
        self.send_command_button.clicked.connect(self.send_selected_command_preset)

        self._pending_send_row = None
        self._click_send_timer = QTimer(self)
        self._click_send_timer.setSingleShot(True)
        self._click_send_timer.timeout.connect(self._fire_pending_send)

        self.command_table.cellClicked.connect(self._on_command_cell_clicked)
        self.command_table.cellDoubleClicked.connect(self._on_command_cell_double_clicked)
        self.command_table.cellChanged.connect(self._on_command_table_cell_changed)





    def _toggle_command_panel(self, expanded: bool) -> None:
        if expanded:
            if not self._command_panel_placed:
                self._position_command_panel()
                self._command_panel_placed = True
            self.command_panel.setVisible(True)
            self.command_panel.raise_()
        else:
            self.command_panel.setVisible(False)
        self.toggle_command_panel_button.setText("命令表 ▼" if expanded else "命令表 ▶")

    def _position_command_panel(self) -> None:
        pw = min(460, max(360, int(self.width() * 0.34)))
        ph = min(420, max(260, int(self.height() * 0.55)))
        margin = 12
        x = max(margin, self.width() - pw - margin)
        y = max(70, margin + 60)
        self.command_panel.setGeometry(x, y, pw, ph)

    def _clamp_command_panel(self) -> None:
        p = self.command_panel
        if not p.isVisible():
            return
        x = max(0, min(p.x(), self.width() - p.width()))
        y = max(0, min(p.y(), self.height() - p.height()))
        if x != p.x() or y != p.y():
            p.move(x, y)

    def resizeEvent(self, event) -> None:
        if self.command_panel.isVisible() and not self._command_panel_placed:
            self._position_command_panel()
            self._command_panel_placed = True
        self._clamp_command_panel()
        super().resizeEvent(event)

    def _on_loop_send_changed(self, state: int) -> None:

        if state == Qt.Checked:
            self.loop_timer.start(self.loop_interval_spin.value())
        else:
            self.loop_timer.stop()


    def _current_receive_limit_bytes(self) -> int:
        selected = self.receive_limit_combo.currentData()
        if isinstance(selected, int) and selected > 0:
            return selected
        return RECEIVE_LIMIT_OPTIONS["10MB"]

    def _trim_receive_area_to_limit(self) -> None:
        limit_bytes = self._current_receive_limit_bytes()
        if self._displayed_text_bytes <= limit_bytes:
            return

        doc = self.receive_area.document()
        while self._displayed_text_bytes > limit_bytes and doc.blockCount() > 1:
            first_block = doc.firstBlock()
            first_text = first_block.text()
            removed_bytes = len((first_text + "\n").encode("utf-8", errors="replace"))

            cursor = QTextCursor(doc)
            cursor.setPosition(first_block.position())
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

            self._displayed_text_bytes = max(0, self._displayed_text_bytes - removed_bytes)

        if self._displayed_text_bytes > limit_bytes and doc.blockCount() <= 1:
            self.receive_area.clear()
            self._displayed_text_bytes = 0

    def select_log_file(self) -> None:
        current_path = self.log_file_path_input.text().strip()
        initial_dir = os.path.dirname(current_path) if current_path else os.path.expanduser("~")
        file_path, _ = QFileDialog.getSaveFileName(self, "选择日志文件", initial_dir, "Text Files (*.txt)")
        if file_path:
            if not file_path.lower().endswith(".txt"):
                file_path += ".txt"
            self.log_file_path_input.setText(file_path)

    def _on_log_to_file_changed(self, state: int) -> None:
        if state != Qt.Checked:
            return

        path = self.log_file_path_input.text().strip()
        if path:
            return

        QMessageBox.warning(self, "提示", "请先选择TXT文件路径")
        self.log_to_file_checkbox.setChecked(False)

    def _append_rx_to_file(self, line: str) -> None:
        if not self.log_to_file_checkbox.isChecked():
            return

        file_path = self.log_file_path_input.text().strip()
        if not file_path:
            return

        try:
            folder = os.path.dirname(file_path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            self._txt_log_write_error_notified = False
        except Exception as e:
            if not self._txt_log_write_error_notified:
                QMessageBox.critical(self, "写入日志失败", str(e))
                self._txt_log_write_error_notified = True
            self.log_to_file_checkbox.setChecked(False)

    def _insert_command_row(self, name: str, content: str) -> None:
        row = self.command_table.rowCount()
        self.command_table.insertRow(row)

        name_item = QTableWidgetItem(name)
        content_item = QTableWidgetItem(content)
        self.command_table.setItem(row, 0, name_item)
        self.command_table.setItem(row, 1, content_item)

    def _collect_command_presets(self) -> list[dict]:
        commands = []
        for row in range(self.command_table.rowCount()):
            name_item = self.command_table.item(row, 0)
            content_item = self.command_table.item(row, 1)
            content = (content_item.text() if content_item else "").strip()
            if not content:
                continue
            name = (name_item.text() if name_item else "").strip() or f"命令{row + 1}"
            commands.append({"name": name, "content": content})
        return commands

    def _save_command_presets(self) -> None:
        commands = self._collect_command_presets()
        try:
            with open(COMMANDS_STORE_PATH, "w", encoding="utf-8") as f:
                json.dump(commands, f, ensure_ascii=False, indent=2)
            self._commands_write_error_notified = False
        except Exception as e:
            if not self._commands_write_error_notified:
                QMessageBox.warning(self, "命令表保存失败", str(e))
                self._commands_write_error_notified = True

    def _normalize_command_lines(self, lines: list[str]) -> list[str]:
        normalized = []
        for raw in lines:
            line = str(raw).strip()
            if not line:
                continue
            if line.startswith("（") and "注意" in line:
                continue
            if line.startswith("#"):
                continue
            line = re.sub(r"（注意：.*?）", "", line).strip()
            if line:
                normalized.append(line)
        return normalized

    def _load_default_command_presets(self) -> None:
        defaults = self._normalize_command_lines(DEFAULT_COMMAND_LINES)
        if not defaults:
            return

        self.command_table.blockSignals(True)
        self.command_table.setRowCount(0)
        for idx, cmd in enumerate(defaults, start=1):
            self._insert_command_row(f"默认{idx}", cmd)
        self.command_table.blockSignals(False)
        self._save_command_presets()

    def _load_command_presets(self) -> None:
        if not os.path.exists(COMMANDS_STORE_PATH):
            self._load_default_command_presets()
            return

        try:
            with open(COMMANDS_STORE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            self._load_default_command_presets()
            return

        if not isinstance(data, list):
            self._load_default_command_presets()
            return

        self.command_table.blockSignals(True)
        self.command_table.setRowCount(0)
        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            name = str(item.get("name", "")).strip() or f"命令{idx + 1}"
            self._insert_command_row(name, content)
        self.command_table.blockSignals(False)

        if self.command_table.rowCount() == 0:
            self._load_default_command_presets()


    def add_command_preset(self) -> None:

        content = self.command_value_input.text().strip() or self.send_input.text().strip()
        if not content:
            QMessageBox.warning(self, "提示", "请输入命令内容")
            return

        name = self.command_name_input.text().strip() or f"命令{self.command_table.rowCount() + 1}"
        self._insert_command_row(name, content)
        self.command_name_input.clear()
        self.command_value_input.clear()
        self._save_command_presets()

    def import_command_presets(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "导入命令",
            os.path.expanduser("~"),
            "Command Files (*.txt *.json);;Text Files (*.txt);;JSON Files (*.json)",
        )
        if not file_path:
            return

        lines: list[str] = []
        try:
            if file_path.lower().endswith(".json"):
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            lines.append(str(item.get("content", "")))
                        else:
                            lines.append(str(item))
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))
            return

        normalized = self._normalize_command_lines(lines)
        if not normalized:
            QMessageBox.information(self, "提示", "未解析到有效命令")
            return

        self.command_table.blockSignals(True)
        self.command_table.setRowCount(0)
        for idx, cmd in enumerate(normalized, start=1):
            self._insert_command_row(f"导入{idx}", cmd)
        self.command_table.blockSignals(False)
        self._save_command_presets()
        QMessageBox.information(self, "导入完成", f"已导入 {len(normalized)} 条命令")

    def remove_selected_command_preset(self) -> None:
        row = self.command_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中要删除的命令")
            return

        self.command_table.removeRow(row)
        self._save_command_presets()


    def send_command_preset_by_row(self, row: int) -> None:
        if row < 0 or row >= self.command_table.rowCount():
            return

        content_item = self.command_table.item(row, 1)
        content = (content_item.text() if content_item else "").strip()
        if not content:
            return

        self._send_text_payload(content)

    def send_selected_command_preset(self) -> None:
        row = self.command_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中要发送的命令")
            return
        self.send_command_preset_by_row(row)

    def _on_command_table_cell_changed(self, _row: int, _column: int) -> None:
        self._save_command_presets()

    def _on_command_cell_clicked(self, row: int, _col: int) -> None:
        if row < 0 or row >= self.command_table.rowCount():
            return
        self._pending_send_row = row
        interval = QApplication.doubleClickInterval()
        self._click_send_timer.start(interval if interval > 0 else 250)

    def _on_command_cell_double_clicked(self, row: int, _col: int) -> None:
        # 双击时取消单击触发的发送，并进入单元格编辑（双击修改）
        self._click_send_timer.stop()
        self._pending_send_row = None
        item = self.command_table.item(row, self.command_table.currentColumn())
        if item is not None:
            self.command_table.editItem(item)

    def _fire_pending_send(self) -> None:
        row = self._pending_send_row
        self._pending_send_row = None
        if row is not None:
            self.send_command_preset_by_row(row)

    def refresh_ports(self) -> None:


        current = self.port_combo.currentText()
        self.port_combo.clear()
        ports = [p.device for p in list_ports.comports()]
        self.port_combo.addItems(ports)
        if current and current in ports:
            self.port_combo.setCurrentText(current)


    def get_config(self) -> SerialConfig:
        return SerialConfig(
            port=self.port_combo.currentText().strip(),
            baud_rate=int(self.baud_combo.currentText().strip()),
            data_bits=DATA_BITS[self.data_bits_combo.currentText()],
            stop_bits_key=self.stop_bits_combo.currentText(),
            parity=PARITY[self.parity_combo.currentText()],
        )

    def toggle_connection(self) -> None:
        if self.serial_port and self.serial_port.is_open:
            self.close_port()
            return

        try:
            cfg = self.get_config()
            if not cfg.port:
                QMessageBox.warning(self, "提示", "请先选择可用串口")
                return

            self.serial_port = serial.Serial(
                port=cfg.port,
                baudrate=cfg.baud_rate,
                bytesize=cfg.data_bits,
                stopbits=STOP_BITS[cfg.stop_bits_key],
                parity=cfg.parity,
                timeout=0.1,
            )

            self.reader_thread = SerialReadThread(self.serial_port)
            self.reader_thread.data_received.connect(self.on_data_received)
            self.reader_thread.error_occurred.connect(self.on_error)
            self.reader_thread.start()

            self.open_button.setText("关闭串口")
            self.update_stats("已连接")
            self.status_changed.emit(f"{self.tab_name} 已连接 {cfg.port}")
        except ValueError:
            QMessageBox.critical(self, "参数错误", "波特率必须是数字")
        except Exception as e:
            QMessageBox.critical(self, "打开串口失败", str(e))

    def close_port(self) -> None:
        if self.reader_thread:
            self.reader_thread.stop()
            self.reader_thread.wait(500)
            self.reader_thread = None

        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()

        self.serial_port = None
        self.open_button.setText("打开串口")
        self.update_stats("未连接")
        self.status_changed.emit(f"{self.tab_name} 已断开")

    def on_error(self, error: str) -> None:
        self.append_log(f"[错误] {error}")
        self.close_port()

    def append_log(self, text: str) -> None:
        self.receive_area.appendPlainText(text)
        self._displayed_text_bytes += len((text + "\n").encode("utf-8", errors="replace"))
        self._trim_receive_area_to_limit()

        if self.auto_scroll_checkbox.isChecked():
            scrollbar = self.receive_area.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())



    def _decode_bytes(self, data: bytes) -> str:
        encoding = self.encoding_combo.currentText().strip() or "gbk"
        try:
            return data.decode(encoding, errors="replace")
        except LookupError:
            return data.decode("gbk", errors="replace")

    @staticmethod
    def _bytes_to_hex(data: bytes) -> str:
        return " ".join(f"{b:02X}" for b in data)

    def _format_rx_text(self, data: bytes) -> str:
        if self.hex_mode_checkbox.isChecked():
            return self._bytes_to_hex(data)
        return self._decode_bytes(data)

    def on_data_received(self, data: bytes) -> None:
        self.rx_count += len(data)
        body = self._format_rx_text(data)

        if self.timestamp_checkbox.isChecked():
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            line = f"[{ts}] RX: {body}"
        else:
            line = body

        self.append_log(line)
        self._append_rx_to_file(line)
        self.update_stats("已连接")


    def _parse_send_payload(self, text: str) -> bytes:
        if self.hex_mode_checkbox.isChecked():
            normalized = re.sub(r"\s+", " ", text.strip())
            if not normalized:
                return b""
            try:
                payload = bytes.fromhex(normalized)
            except ValueError as e:
                raise ValueError("HEX格式错误，请输入如: 01 A0 FF") from e
            if self.add_newline_checkbox.isChecked():
                payload += b"\r\n"
            return payload

        if self.add_newline_checkbox.isChecked():
            text += "\r\n"

        encoding = self.encoding_combo.currentText().strip() or "gbk"
        try:
            return text.encode(encoding, errors="replace")
        except LookupError:
            return text.encode("gbk", errors="replace")

    def _send_text_payload(self, text: str) -> bool:
        if not text:
            return False

        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "提示", "请先打开串口")
            return False

        try:
            payload = self._parse_send_payload(text)
            if not payload:
                return False

            sent = self.serial_port.write(payload)
            self.tx_count += sent

            if self.timestamp_checkbox.isChecked():
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                tx_body = self._bytes_to_hex(payload) if self.hex_mode_checkbox.isChecked() else text
                self.append_log(f"[{ts}] TX: {tx_body}")

            self.update_stats("已连接")
            return True
        except ValueError as e:
            QMessageBox.warning(self, "发送参数错误", str(e))
            return False
        except Exception as e:
            QMessageBox.critical(self, "发送失败", str(e))
            return False

    def send_data(self) -> None:
        text = self.send_input.text().strip()
        self._send_text_payload(text)


    def find_text(self, forward: bool = True) -> None:
        keyword = self.search_input.text().strip()
        if not keyword:
            self.clear_highlight()
            return

        flags = QTextDocument.FindFlag()
        if not forward:
            flags |= QTextDocument.FindBackward

        found = self.receive_area.find(keyword, flags)
        if not found:
            cursor = self.receive_area.textCursor()
            cursor.movePosition(QTextCursor.Start if forward else QTextCursor.End)
            self.receive_area.setTextCursor(cursor)
            found = self.receive_area.find(keyword, flags)

        if found:
            self.highlight_all_matches(current_cursor=self.receive_area.textCursor(), force_focus=False)

    def highlight_all_matches(self, current_cursor: Optional[QTextCursor] = None, force_focus: bool = True) -> None:
        keyword = self.search_input.text().strip()
        if not keyword:
            self.clear_highlight()
            return

        doc = self.receive_area.document()
        selections = []
        search_cursor = QTextCursor(doc)

        normal_fmt = QTextCharFormat()
        normal_fmt.setBackground(QColor("#FFB300"))
        normal_fmt.setForeground(QColor("#1A1A1A"))

        current_fmt = QTextCharFormat()
        current_fmt.setBackground(QColor("#FF7A00"))
        current_fmt.setForeground(QColor("#111111"))

        current_start = -1
        current_end = -1
        if current_cursor and not current_cursor.isNull() and current_cursor.hasSelection():
            current_start = current_cursor.selectionStart()
            current_end = current_cursor.selectionEnd()

        while True:
            search_cursor = doc.find(keyword, search_cursor)
            if search_cursor.isNull():
                break

            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(search_cursor)

            if (
                current_start >= 0
                and search_cursor.selectionStart() == current_start
                and search_cursor.selectionEnd() == current_end
            ):
                selection.format = current_fmt
            else:
                selection.format = normal_fmt

            selections.append(selection)

        self.receive_area.setExtraSelections(selections)
        if force_focus:
            self.receive_area.setFocus(Qt.OtherFocusReason)
        self.receive_area.viewport().update()



    def clear_highlight(self) -> None:
        self.receive_area.setExtraSelections([])

    def clear_receive_area(self) -> None:
        self.receive_area.clear()
        self._displayed_text_bytes = 0
        self.clear_highlight()


    def update_stats(self, status_text: str) -> None:
        self.stats_label.setText(f"RX: {self.rx_count} bytes | TX: {self.tx_count} bytes | {status_text}")

    def shutdown(self) -> None:
        self.loop_timer.stop()
        self.close_port()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("简约串口助手")
        self.resize(1280, 760)
        self.tab_count = 0

        central = QWidget()
        layout = QVBoxLayout(central)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        self.title_label = QLabel("简约串口助手")
        self.title_label.setStyleSheet("font-weight: 600;")
        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.add_left_button = QPushButton("新增左侧标签")
        self.add_right_button = QPushButton("新增右侧标签")
        self.remove_left_button = QPushButton("关闭左侧当前")
        self.remove_right_button = QPushButton("关闭右侧当前")
        self.global_refresh_button = QPushButton("刷新全部串口")

        top_bar.addWidget(self.title_label)
        top_bar.addWidget(self.status_label)
        top_bar.addStretch(1)
        top_bar.addWidget(self.add_left_button)
        top_bar.addWidget(self.add_right_button)
        top_bar.addWidget(self.remove_left_button)
        top_bar.addWidget(self.remove_right_button)
        top_bar.addWidget(self.global_refresh_button)

        self.left_tabs = QTabWidget()

        self.right_tabs = QTabWidget()
        self.left_tabs.setTabsClosable(False)
        self.right_tabs.setTabsClosable(False)

        self.content_widget = QWidget()
        self.content_layout = QHBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)
        self.content_layout.addWidget(self.left_tabs, 1)
        self.content_layout.addWidget(self.right_tabs, 1)

        layout.addLayout(top_bar)
        layout.addWidget(self.content_widget, 1)
        self.setCentralWidget(central)


        self.add_left_button.clicked.connect(lambda: self.add_serial_tab("left"))
        self.add_right_button.clicked.connect(lambda: self.add_serial_tab("right"))
        self.remove_left_button.clicked.connect(lambda: self.remove_current_tab("left"))
        self.remove_right_button.clicked.connect(lambda: self.remove_current_tab("right"))
        self.global_refresh_button.clicked.connect(self.refresh_all_ports)

        self.add_serial_tab("left")

    def _next_tab_name(self) -> str:
        self.tab_count += 1
        return f"串口{self.tab_count}"

    def _total_tabs(self) -> int:
        return self.left_tabs.count() + self.right_tabs.count()

    def _pop_tab(self, source_tabs: QTabWidget, index: int):
        widget = source_tabs.widget(index)
        title = source_tabs.tabText(index)
        source_tabs.removeTab(index)
        return widget, title

    def _sync_split_view(self) -> None:
        total = self._total_tabs()

        if total <= 1:
            if self.left_tabs.count() == 0 and self.right_tabs.count() == 1:
                widget, title = self._pop_tab(self.right_tabs, 0)
                self.left_tabs.addTab(widget, title)
                self.left_tabs.setCurrentWidget(widget)

            self.right_tabs.hide()
        else:
            if self.left_tabs.count() == 0 and self.right_tabs.count() > 0:
                widget, title = self._pop_tab(self.right_tabs, 0)
                self.left_tabs.addTab(widget, title)
            elif self.right_tabs.count() == 0 and self.left_tabs.count() > 1:
                widget, title = self._pop_tab(self.left_tabs, self.left_tabs.count() - 1)
                self.right_tabs.addTab(widget, title)

            self.right_tabs.show()

        self.remove_left_button.setEnabled(self.left_tabs.count() > 0)
        self.remove_right_button.setEnabled(self.right_tabs.count() > 0)

    def add_serial_tab(self, side: str) -> None:
        name = self._next_tab_name()
        tab = SerialTab(name)
        tab.status_changed.connect(self.status_label.setText)

        if self._total_tabs() == 1:
            target_tabs = self.right_tabs if self.left_tabs.count() == 1 else self.left_tabs
        else:
            target_tabs = self.left_tabs if side == "left" else self.right_tabs

        target_tabs.addTab(tab, name)
        target_tabs.setCurrentWidget(tab)
        self._sync_split_view()

    def remove_current_tab(self, side: str) -> None:
        target_tabs = self.left_tabs if side == "left" else self.right_tabs
        current_idx = target_tabs.currentIndex()
        if current_idx < 0:
            return

        widget = target_tabs.widget(current_idx)
        if isinstance(widget, SerialTab):
            widget.shutdown()
        target_tabs.removeTab(current_idx)
        widget.deleteLater()
        self._sync_split_view()

    def _iter_all_serial_tabs(self):
        for tabs in (self.left_tabs, self.right_tabs):
            for i in range(tabs.count()):
                widget = tabs.widget(i)
                if isinstance(widget, SerialTab):
                    yield widget

    def refresh_all_ports(self) -> None:
        for tab in self._iter_all_serial_tabs():
            tab.refresh_ports()
        self.status_label.setText("已刷新全部串口列表")

    def closeEvent(self, event) -> None:
        for tab in self._iter_all_serial_tabs():
            tab.shutdown()
        super().closeEvent(event)




def main() -> None:
    app = QApplication(sys.argv)
    icon_path = resource_path(os.path.join("assets", "app.ico"))
    icon = QIcon(icon_path)
    if not icon.isNull():
        app.setWindowIcon(icon)

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())



if __name__ == "__main__":
    main()
