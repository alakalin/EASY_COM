"""简约串口助手 —— Python / PySide6 版

功能概览
    多标签串口调试（左右分屏，可自由增删）
    串口参数配置、HEX 收发、定时发送、时间戳
    接收区关键字搜索 / 高亮、接收上限裁剪、实时写 TXT
    悬浮命令表（可拖动 / 单击发送 / 双击编辑 / 导入导出）
    浅色 / 深色主题切换（选择会持久化到用户目录）

代码结构
    1. 常量与配置读写
    2. 主题系统（Theme / build_palette / build_qss）
    3. 串口读取线程 SerialReadThread
    4. 悬浮命令面板 FloatingCommandPanel
    5. 单串口页 SerialTab
    6. 主窗口 MainWindow
    7. 程序入口 main()
"""

import ctypes
import json
import os
import re
import string
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

try:
    import ctypes.wintypes
except ImportError:  # 非 Windows 平台没有 wintypes，边缘缩放会自动跳过
    pass

import serial
from PySide6.QtCore import QPoint, QRect, QThread, QTimer, Qt, Signal
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
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from serial.tools import list_ports


# ---------------------------------------------------------------------------
# 1. 常量与配置读写
# ---------------------------------------------------------------------------

APP_NAME = "简约串口助手"
APP_VERSION = "3.0.0"

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
ENCODINGS = ["gbk", "gb18030", "utf-8"]

RECEIVE_LIMIT_OPTIONS = {
    "512KB": 512 * 1024,
    "1MB": 1 * 1024 * 1024,
    "10MB": 10 * 1024 * 1024,
    "40MB": 40 * 1024 * 1024,
}

# 接收合并：把一小段时间内连续到达的数据拼成一条输出。
# 串口是按字节流渐进到达的，一条长报文（比如 300 字节 @115200 要约 26ms）
# 会被读线程切成好几批，逐批显示就会出现"报文中间插进一个时间戳"的怪象。
# 这里用空闲超时判断边界：只要还在持续来数据就继续攒，安静超过阈值才输出。
RX_MERGE_OPTIONS = {
    "关闭": 0,
    "30ms": 30,
    "50ms": 50,
    "100ms": 100,
    "200ms": 200,
}
DEFAULT_RX_MERGE_LABEL = "50ms"
# 缓冲上限：遇到永不空闲的连续流时，攒到这里就强制输出，免得延迟无限拉长
RX_MERGE_MAX_BYTES = 4096

# 命令表列索引
COMMAND_NAME_COLUMN = 0
COMMAND_CONTENT_COLUMN = 1
COMMAND_EDIT_COLUMN = 2

# 命令表 / 主题等偏好统一放在用户目录，避免污染程序目录（打包后目录可能只读）
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".serial_assistant")
COMMANDS_STORE_PATH = os.path.join(CONFIG_DIR, "commands.json")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

# 兼容上一版遗留的命令表位置，首次启动时自动迁移
LEGACY_COMMANDS_STORE_PATH = os.path.join(os.path.expanduser("~"), ".serial_assistant_commands.json")

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

# 接收区一次裁剪后保留的比例（留出余量，避免每收一包都触发文档重排）
TRIM_KEEP_RATIO = 0.8

# 无边框窗口自己实现边缘缩放时用到的 Windows 消息与命中返回值
WM_NCHITTEST = 0x0084
HT_LEFT, HT_RIGHT, HT_TOP, HT_BOTTOM = 10, 11, 12, 15
HT_TOPLEFT, HT_TOPRIGHT, HT_BOTTOMLEFT, HT_BOTTOMRIGHT = 13, 14, 16, 17
RESIZE_MARGIN = 6


def resource_path(relative_path: str) -> str:
    """获取资源绝对路径，兼容 PyInstaller 打包后的临时目录。"""
    # 打包后资源在 _MEIPASS；未打包时以本文件所在目录为基准（不能用 cwd，否则依赖启动目录）
    base_path = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def load_config() -> dict:
    """读取用户配置，任何异常都退回空配置。"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(updates: dict) -> None:
    """把若干键值合并写回用户配置文件。"""
    data = load_config()
    data.update(updates)
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        # 配置写不进去不应该影响主流程（例如用户目录只读）
        pass


def read_text_file(file_path: str) -> str:
    """尽力读取文本文件，依次尝试 utf-8 / gbk / gb18030。

    导入命令表时用户手上的文件常常是 GBK 编码（设备侧文档），
    直接按 utf-8 读会抛 UnicodeDecodeError 并给出一个没头没脑的报错。
    """
    last_error: Optional[Exception] = None
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError as e:
            last_error = e
            continue
        except Exception:
            raise
    if last_error:
        raise last_error
    return ""


def connect_check_state(widget: QCheckBox, handler) -> None:
    """把复选框的勾选变化接到 `handler(checked: bool)`。

    这里刻意绕开 `stateChanged`：它在 Qt 6.7 之前传 int(0/2)，
    而 PySide6 的 `Qt.Checked` 是 CheckState 枚举，`2 == Qt.Checked` 恒为 False，
    老写法会导致分支永远走不进去（定时发送勾了不动、路径校验永不执行）。
    """
    if hasattr(widget, "checkStateChanged"):
        widget.checkStateChanged.connect(lambda state: handler(state == Qt.CheckState.Checked))
    else:  # Qt < 6.7 兜底
        widget.stateChanged.connect(lambda state: handler(state == Qt.CheckState.Checked.value))


@dataclass
class SerialConfig:
    """串口连接参数。"""

    port: str
    baud_rate: int
    data_bits: int
    stop_bits_key: str
    parity: str


# ---------------------------------------------------------------------------
# 2. 主题系统
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Theme:
    """一套完整配色。字段名同时作为 QSS 模板的占位符。"""

    key: str
    label: str
    is_dark: bool

    window_bg: str          # 主窗口底色
    panel_bg: str           # 标题栏 / 悬浮命令面板底色
    page_bg: str            # 标签页内容区底色（按钮、输入框之外的留白）
    textarea_bg: str        # 接收区底色
    input_bg: str           # 输入类控件底色
    input_bg_disabled: str
    alt_row_bg: str         # 表格隔行底色
    button_bg: str
    button_hover: str
    button_pressed: str
    table_header_bg: str
    tab_bg: str
    tab_selected_bg: str

    border: str
    border_focus: str
    text: str
    text_dim: str
    text_disabled: str

    accent: str             # 主强调色，用于需要实心填充的场景
    accent_text: str        # 文字/图标上的强调色，与 accent 分开取色阶
    accent_hover: str
    accent_pressed: str
    accent_fg: str          # 强调色实心块上的前景色
    accent_soft_bg: str     # 强调色的淡化底，用于选中态按钮，避免大面积纯色块

    panel_title_bg: str     # 悬浮命令面板标题栏
    panel_title_hover_bg: str
    panel_title_fg: str
    panel_border: str

    selection_bg: str       # 文本框选中色
    selection_fg: str
    highlight_bg: str       # 搜索高亮
    highlight_fg: str
    highlight_current_bg: str
    highlight_current_fg: str

    scrollbar_bg: str
    scrollbar_handle: str
    scrollbar_handle_hover: str

    shadow_alpha: int       # 悬浮面板投影浓度


# 以下色值取自 Radix Colors 色阶（WorkBuddy 同源），注释标注了对应的色阶编号，
# 便于后续微调时定位：色阶语义依次为
#   1 应用背景 / 2 次级背景 / 3 控件背景 / 4 hover / 5 active
#   6 分隔线与边框 / 7 边框-hover / 8 边框-焦点 / 9 实心主色 / 10 实心-hover
#   11 低对比文字 / 12 高对比文字
LIGHT_THEME = Theme(
    key="light",
    label="浅色",
    is_dark=False,
    window_bg="#f9f9f9",            # gray-2
    panel_bg="#ffffff",
    page_bg="#ffffff",
    textarea_bg="#ffffff",
    input_bg="#ffffff",
    input_bg_disabled="#f0f0f0",    # gray-3
    alt_row_bg="#f9f9f9",           # gray-2
    button_bg="#ffffff",
    button_hover="#f0f0f0",         # gray-3
    button_pressed="#e8e8e8",       # gray-4
    table_header_bg="#f0f0f0",      # gray-3
    tab_bg="#f0f0f0",               # gray-3
    tab_selected_bg="#ffffff",
    border="#d9d9d9",               # gray-6
    border_focus="#f76b15",         # orange-9
    text="#202020",                 # gray-12
    text_dim="#646464",             # gray-11
    text_disabled="#8d8d8d",        # gray-9
    accent="#f76b15",               # orange-9
    accent_text="#cc4e00",          # orange-11
    accent_hover="#ef5f00",         # orange-10
    accent_pressed="#cc4e00",       # orange-11
    accent_fg="#ffffff",
    accent_soft_bg="#ffefd6",       # orange-3
    panel_title_bg="#cc4e00",       # orange-11
    panel_title_hover_bg="#582d1d",  # orange-12
    panel_title_fg="#ffffff",
    panel_border="#f76b15",         # orange-9
    selection_bg="#ffdfb5",         # orange-4
    selection_fg="#582d1d",         # orange-12
    highlight_bg="#ffdfb5",         # orange-4
    highlight_fg="#582d1d",         # orange-12
    highlight_current_bg="#f76b15",  # orange-9
    highlight_current_fg="#ffffff",
    scrollbar_bg="#f9f9f9",         # gray-2
    scrollbar_handle="#bbbbbb",     # gray-8
    scrollbar_handle_hover="#8d8d8d",  # gray-9
    shadow_alpha=70,
)

DARK_THEME = Theme(
    key="dark",
    label="深色",
    is_dark=True,
    window_bg="#111111",            # gray-1 (dark)
    panel_bg="#191919",             # gray-2
    page_bg="#191919",              # gray-2
    textarea_bg="#111111",          # gray-1，接收区做成最暗的"画布"
    input_bg="#222222",             # gray-3
    input_bg_disabled="#191919",    # gray-2
    alt_row_bg="#191919",           # gray-2
    button_bg="#222222",            # gray-3
    button_hover="#2a2a2a",         # gray-4
    button_pressed="#313131",       # gray-5
    table_header_bg="#222222",      # gray-3
    tab_bg="#191919",               # gray-2
    tab_selected_bg="#111111",      # gray-1
    border="#3a3a3a",               # gray-6
    border_focus="#f76b15",         # orange-9
    text="#eeeeee",                 # gray-12
    text_dim="#b4b4b4",             # gray-11
    text_disabled="#6e6e6e",        # gray-9
    accent="#f76b15",               # orange-9
    accent_text="#ffa057",          # orange-11 (dark)，深底上做文字要更亮
    accent_hover="#ff801f",         # orange-10 (dark)
    accent_pressed="#ef5f00",       # orange-10
    accent_fg="#1a1a1a",
    accent_soft_bg="#331e0b",       # orange-3 (dark)
    panel_title_bg="#a35829",       # orange-8 (dark)
    panel_title_hover_bg="#7e451d",  # orange-7 (dark)
    panel_title_fg="#ffffff",
    panel_border="#f76b15",         # orange-9
    selection_bg="#562800",         # orange-5 (dark)
    selection_fg="#ffe0c2",         # orange-12 (dark)
    highlight_bg="#66350c",         # orange-6 (dark)
    highlight_fg="#ffe0c2",         # orange-12 (dark)
    highlight_current_bg="#f76b15",  # orange-9
    highlight_current_fg="#1a1a1a",
    scrollbar_bg="#111111",         # gray-1
    scrollbar_handle="#484848",     # gray-7
    scrollbar_handle_hover="#606060",  # gray-8
    shadow_alpha=170,
)

# 中性色用 Radix olive（带极轻微绿调的灰），主色用 Radix green，
# 整体就是 WorkBuddy 当前的配色观感
GREEN_THEME = Theme(
    key="green",
    label="绿色",
    is_dark=False,
    window_bg="#f8faf8",            # olive-2
    panel_bg="#ffffff",
    page_bg="#f4fbf6",              # green-2，内容区留白也带绿，整页统一绿调
    textarea_bg="#e6f6eb",          # green-3，接收区用明显的淡绿底，和浅色主题拉开
    input_bg="#ffffff",
    input_bg_disabled="#eff1ef",    # olive-3
    alt_row_bg="#f4fbf6",           # green-2
    button_bg="#ffffff",
    button_hover="#eff1ef",         # olive-3
    button_pressed="#e7e9e7",       # olive-4
    table_header_bg="#eff1ef",      # olive-3
    tab_bg="#eff1ef",               # olive-3
    tab_selected_bg="#ffffff",
    border="#d7dad7",               # olive-6
    border_focus="#30a46c",         # green-9
    text="#1d211c",                 # olive-12
    text_dim="#60655f",             # olive-11
    text_disabled="#898e87",        # olive-9
    accent="#30a46c",               # green-9
    accent_text="#218358",          # green-11
    accent_hover="#2b9a66",         # green-10
    accent_pressed="#218358",       # green-11
    accent_fg="#ffffff",
    accent_soft_bg="#e6f6eb",       # green-3
    panel_title_bg="#218358",       # green-11
    panel_title_hover_bg="#193b2d",  # green-12
    panel_title_fg="#ffffff",
    panel_border="#30a46c",         # green-9
    selection_bg="#d6f1df",         # green-4
    selection_fg="#193b2d",         # green-12
    highlight_bg="#d6f1df",         # green-4
    highlight_fg="#193b2d",         # green-12
    highlight_current_bg="#30a46c",  # green-9
    highlight_current_fg="#ffffff",
    scrollbar_bg="#f8faf8",         # olive-2
    scrollbar_handle="#b9bcb8",     # olive-8
    scrollbar_handle_hover="#898e87",  # olive-9
    shadow_alpha=70,
)

THEME_LIST = (LIGHT_THEME, DARK_THEME, GREEN_THEME)
THEMES = {t.key: t for t in THEME_LIST}
# 默认使用绿色主题；用户在标题栏的选择会覆盖它并被记住
DEFAULT_THEME_KEY = GREEN_THEME.key


_QSS_TEMPLATE = string.Template("""
QMainWindow, QDialog, QMessageBox { background-color: $window_bg; }
/* 无边框窗口没有系统边框，深色壁纸下会糊在背景里，补一圈描边 */
QMainWindow { border: 1px solid $border; }

/*
 * 自定义标题栏（无边框窗口）。标签一律不参与鼠标事件，
 * 这样在文字上按住也能拖动窗口，只有按钮区域会被拦截。
 */
#titleBar { background-color: $panel_bg; border-bottom: 1px solid $border; }
#titleBar QLabel { color: $text_dim; }
#titleBar #appTitle { font-size: 15px; font-weight: 700; color: $accent_text; }

QLabel { background: transparent; color: $text; }
QLabel:disabled { color: $text_disabled; }
#appTitle { font-size: 15px; font-weight: 700; color: $accent_text; }
#statusLabel, #statsLabel { color: $text_dim; }

QPushButton#windowButton, QPushButton#windowCloseButton {
    background: transparent;
    border: none;
    color: $text;
    font-size: 13px;
    padding: 0px;
    border-radius: 3px;
}
QPushButton#windowButton:hover { background-color: $button_hover; }
QPushButton#windowButton:pressed { background-color: $button_pressed; }
QPushButton#windowCloseButton:hover { background-color: #E81123; color: #FFFFFF; }
QPushButton#windowCloseButton:pressed { background-color: #B10F1B; color: #FFFFFF; }
/*
 * 日志记录状态：未记录时低调，记录中用强调色打底，保证一眼能看到。
 * 属性选择器依赖 QSS 的 [state="..."]，改属性后需要 unpolish/polish 才会重算。
 */
#logStatusLabel { color: $text_disabled; padding: 1px 8px; border-radius: 3px; }
#logStatusLabel[state="active"] { color: $accent_text; background-color: $accent_soft_bg; font-weight: 700; }

QPushButton {
    background-color: $button_bg;
    color: $text;
    border: 1px solid $border;
    border-radius: 4px;
    padding: 4px 10px;
}
QPushButton:hover { background-color: $button_hover; border-color: $accent; }
QPushButton:pressed { background-color: $button_pressed; }
QPushButton:checked { background-color: $accent_soft_bg; border-color: $accent; color: $accent_text; font-weight: 700; }
QPushButton:checked:hover { border-color: $accent_hover; color: $accent_text; }
QPushButton:disabled { color: $text_disabled; background-color: $input_bg_disabled; border-color: $border; }

QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QTableWidget {
    background-color: $input_bg;
    color: $text;
    border: 1px solid $border;
    border-radius: 4px;
    selection-background-color: $selection_bg;
    selection-color: $selection_fg;
}
QLineEdit, QComboBox { padding: 3px 6px; }
QPlainTextEdit, QTextEdit { background-color: $textarea_bg; padding: 2px; }
#receiveArea { font-family: Consolas, "Courier New", monospace; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus { border: 1px solid $border_focus; }
QLineEdit:disabled, QComboBox:disabled, QPlainTextEdit:disabled, QTextEdit:disabled { color: $text_disabled; background-color: $input_bg_disabled; }
QComboBox QAbstractItemView {
    background-color: $input_bg;
    color: $text;
    border: 1px solid $border;
    selection-background-color: $accent;
    selection-color: $accent_fg;
    outline: none;
}

QSpinBox { background-color: $input_bg; color: $text; border: 1px solid $border; border-radius: 4px; padding: 2px 4px; }
QSpinBox:focus { border: 1px solid $border_focus; }

QCheckBox { background: transparent; color: $text; spacing: 6px; }
QCheckBox:disabled { color: $text_disabled; }
/*
 * Fusion 原生指示器在浅色下和窗口底色几乎同色，未勾选的框基本看不见，
 * 所以这里显式接管。注意不能在这里放 data: URI 的 SVG 图标——Qt 的样式表
 * 解析器会因此报错并丢掉整张表，勾选态改用实心色块表达。
 */
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid $border; border-radius: 3px; background-color: $input_bg; }
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked { background-color: $accent; border-color: $accent_pressed; }
QCheckBox::indicator:checked:hover { background-color: $accent_hover; }
QCheckBox::indicator:disabled { background-color: $input_bg_disabled; border-color: $border; }

QTabWidget::pane { border: 1px solid $border; background-color: $page_bg; border-radius: 4px; top: -1px; }
QTabBar::tab {
    background-color: $tab_bg;
    color: $text_dim;
    border: 1px solid $border;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 5px 16px;
    margin-right: 2px;
}
QTabBar::tab:selected { background-color: $tab_selected_bg; color: $accent_text; font-weight: 700; }
QTabBar::tab:hover:!selected { background-color: $button_hover; color: $text; }

QHeaderView::section {
    background-color: $table_header_bg;
    color: $text;
    border: none;
    border-right: 1px solid $border;
    border-bottom: 1px solid $border;
    padding: 4px 6px;
}
QTableWidget { alternate-background-color: $alt_row_bg; gridline-color: $border; }
QTableWidget::item { padding: 2px 4px; }
QTableWidget::item:selected { background-color: $accent; color: $accent_fg; }

/* 命令表行尾的编辑小图标 */
QPushButton#tableEditButton {
    background: transparent;
    border: none;
    color: $text_dim;
    font-size: 14px;
    padding: 0px;
    border-radius: 3px;
}
QPushButton#tableEditButton:hover { background-color: $accent_soft_bg; color: $accent_text; }

QScrollBar:vertical { background: $scrollbar_bg; width: 12px; margin: 0; border: none; }
QScrollBar::handle:vertical { background: $scrollbar_handle; min-height: 24px; border-radius: 6px; margin: 2px; }
QScrollBar::handle:vertical:hover { background: $scrollbar_handle_hover; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; width: 0; background: none; border: none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QScrollBar:horizontal { background: $scrollbar_bg; height: 12px; margin: 0; border: none; }
QScrollBar::handle:horizontal { background: $scrollbar_handle; min-width: 24px; border-radius: 6px; margin: 2px; }
QScrollBar::handle:horizontal:hover { background: $scrollbar_handle_hover; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { height: 0; width: 0; background: none; border: none; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

QToolTip { background-color: $input_bg; color: $text; border: 1px solid $border; padding: 3px 6px; }
""")


def build_qss(theme: Theme) -> str:
    """由主题生成全局样式表。"""
    return _QSS_TEMPLATE.substitute(asdict(theme))


def build_palette(theme: Theme) -> QPalette:
    """由主题生成调色板。

    QSS 只能覆盖它显式声明过的部件，下拉箭头、复选框指示器、表格栅格这些
    由 style 自绘的部分仍读调色板，所以两者必须一起设置，深色下才不会出现
    "黑底黑箭头"这类看不清的情况。
    """
    p = QPalette()
    role = QPalette.ColorRole
    group = QPalette.ColorGroup

    mapping = {
        role.Window: theme.window_bg,
        role.WindowText: theme.text,
        role.Base: theme.input_bg,
        role.AlternateBase: theme.alt_row_bg,
        role.Text: theme.text,
        role.Button: theme.button_bg,
        role.ButtonText: theme.text,
        role.BrightText: "#FF5252",
        role.Highlight: theme.accent,
        role.HighlightedText: theme.accent_fg,
        role.ToolTipBase: theme.input_bg,
        role.ToolTipText: theme.text,
        role.Link: theme.accent,
        role.Mid: theme.border,
        role.Dark: theme.border,
        role.Shadow: theme.window_bg,
    }
    if hasattr(role, "PlaceholderText"):
        mapping[role.PlaceholderText] = theme.text_dim

    for r, color in mapping.items():
        p.setColor(r, QColor(color))

    for r in (role.WindowText, role.Text, role.ButtonText, role.HighlightedText):
        p.setColor(group.Disabled, r, QColor(theme.text_disabled))

    return p


def apply_global_theme(app: QApplication, theme: Theme) -> None:
    """把主题应用到整个应用。"""
    if app.style().objectName().lower() != "fusion":
        # Fusion 自绘比例最高，跨平台的深色表现最一致
        app.setStyle("Fusion")
    app.setPalette(build_palette(theme))
    app.setStyleSheet(build_qss(theme))


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


# ---------------------------------------------------------------------------
# 3. 串口读取线程
# ---------------------------------------------------------------------------

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
                # 串口被主线程关闭后 is_open 会变 False，这里主动退出避免刷错误
                if not self.serial_port.is_open:
                    break
                waiting = self.serial_port.in_waiting
                if waiting > 0:
                    data = self.serial_port.read(waiting)
                    if data:
                        self.data_received.emit(data)
                else:
                    self.msleep(20)
            except Exception as e:
                if self._running:
                    self.error_occurred.emit(str(e))
                break


# ---------------------------------------------------------------------------
# 4. 悬浮命令面板
# ---------------------------------------------------------------------------

class _CommandPanelTitleBar(QWidget):
    """悬浮命令面板的标题栏，负责拖动与关闭按钮。"""

    def __init__(self, panel: "FloatingCommandPanel") -> None:
        super().__init__(panel)
        self._panel = panel
        self._drag_offset = None
        self.setFixedHeight(30)
        self.setObjectName("commandPanelTitleBar")
        _set_opaque_background(self, LIGHT_THEME.panel_title_bg)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(6)

        self.title_label = QLabel("命令表")
        self.title_label.setStyleSheet("font-weight:600;")
        self.setToolTip("按住可拖动面板位置，双击复位到默认位置")

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
            self._panel.raise_()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and (event.buttons() & Qt.LeftButton):
            global_pos = event.globalPosition().toPoint()
            parent = self._panel.parentWidget()
            local_pos = parent.mapFromGlobal(global_pos - self._drag_offset)
            # 必须逐帧夹回父控件内部：面板被拖出所属标签页后，
            # 超出的部分会被相邻标签页盖住，标题栏抓不到就等于"拖进去出不来"
            self._panel.move(self._panel.clamp_position(local_pos))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """双击标题栏复位到默认位置，作为拖丢之后的兜底逃生口。"""
        if event.button() == Qt.LeftButton:
            self._drag_offset = None
            self._panel.apply_default_geometry()
            self._panel.raise_()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class FloatingCommandPanel(QWidget):
    """不进入主布局的悬浮命令面板，叠加显示，可拖动、可关闭。"""

    MIN_WIDTH = 360
    MIN_HEIGHT = 240

    def __init__(self, parent: Optional[QWidget] = None, theme: Theme = LIGHT_THEME) -> None:
        super().__init__(parent)
        self.setObjectName("floatingCommandPanel")
        self._theme = theme
        _set_opaque_background(self, theme.panel_bg)
        self.setMinimumWidth(self.MIN_WIDTH)
        self.setMinimumHeight(self.MIN_HEIGHT)
        self.resize(440, 380)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        self.title_bar = _CommandPanelTitleBar(self)
        self.body = QWidget()
        self.body.setObjectName("floatingCommandPanelBody")
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(8, 6, 8, 8)
        body_layout.setSpacing(6)

        outer.addWidget(self.title_bar)
        outer.addWidget(self.body, 1)

        self._body_layout = body_layout
        self.close_button = self.title_bar.close_button

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(20)
        self._shadow.setOffset(0, 4)
        self.setGraphicsEffect(self._shadow)

        self.apply_theme(theme)

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    # -- 定位 -------------------------------------------------------------

    def clamp_position(self, pos: QPoint) -> QPoint:
        """把面板位置夹在父控件内部。

        面板是 SerialTab 的浮动子控件，一旦被拖到所属标签页之外，超出部分
        会被相邻标签页盖住，标题栏抓不到就再也拖不回来。所有移动路径都要过这里。
        """
        parent = self.parentWidget()
        if parent is None:
            return pos
        max_x = max(0, parent.width() - self.width())
        max_y = max(0, parent.height() - self.height())
        return QPoint(min(max(0, pos.x()), max_x), min(max(0, pos.y()), max_y))

    def apply_default_geometry(self) -> None:
        """按父控件尺寸重算默认悬浮位置与大小，用于首次展开和双击复位。"""
        parent = self.parentWidget()
        if parent is None:
            return
        avail_w = max(240, parent.width() - 16)
        avail_h = max(180, parent.height() - 16)
        pw = min(460, max(self.MIN_WIDTH, int(parent.width() * 0.34)), avail_w)
        ph = min(420, max(self.MIN_HEIGHT, int(parent.height() * 0.55)), avail_h)
        margin = 12
        x = max(margin, parent.width() - pw - margin)
        y = min(70, max(0, parent.height() - ph))
        self.setGeometry(x, y, pw, ph)
        self.move(self.clamp_position(QPoint(x, y)))

    def clamp_into_parent(self) -> None:
        """父控件尺寸变化后，把面板收进可见区域。

        如果父控件已经比面板的最小尺寸还小，必须先收缩面板本身：否则
        clamp_position 会把位置死锁在 (0, 0)，用户怎么拖都会被弹回去，
        表现出来就是"面板卡住、拖不动也关不掉"。典型触发场景是单标签时把
        面板拖到最右侧，然后新增一个右侧标签、可用宽度直接减半。
        """
        parent = self.parentWidget()
        if parent is None or not self.isVisible():
            return

        avail_w = max(240, parent.width() - 8)
        avail_h = max(180, parent.height() - 8)
        self.setMinimumWidth(min(self.MIN_WIDTH, avail_w))
        self.setMinimumHeight(min(self.MIN_HEIGHT, avail_h))
        if self.width() > avail_w or self.height() > avail_h:
            self.resize(min(self.width(), avail_w), min(self.height(), avail_h))
        self.move(self.clamp_position(self.pos()))

    def apply_theme(self, theme: Theme) -> None:
        """面板带内联样式与投影，需要跟随主题单独刷新。"""
        self._theme = theme
        _set_opaque_background(self, theme.panel_bg)
        _set_opaque_background(self.title_bar, theme.panel_title_bg)
        _set_opaque_background(self.body, theme.panel_bg)
        self._shadow.setColor(QColor(0, 0, 0, theme.shadow_alpha))

        self.setStyleSheet(
            "#floatingCommandPanel {"
            f"  background: {theme.panel_bg}; border: 2px solid {theme.panel_border}; border-radius: 8px;"
            "}"
            "#floatingCommandPanelBody {"
            f"  background: {theme.panel_bg}; border: none;"
            "}"
            "#commandPanelTitleBar {"
            f"  background: {theme.panel_title_bg};"
            "  border-top-left-radius: 6px; border-top-right-radius: 6px;"
            "}"
            f"#commandPanelTitleBar QLabel {{ border: none; background: transparent; color: {theme.panel_title_fg}; font-weight: 700; }}"
            "#commandPanelCloseButton {"
            f"  border: none; background: transparent; font-weight: 700; color: {theme.panel_title_fg};"
            "}"
            "#commandPanelCloseButton:hover {"
            f"  background: {theme.panel_title_hover_bg}; color: #FFFFFF; border-radius: 4px;"
            "}"
        )


# ---------------------------------------------------------------------------
# 5. 单串口页
# ---------------------------------------------------------------------------

def format_port_label(info) -> str:
    """把端口信息拼成设备管理器里的那种名字，如 `USB-SERIAL CH340 (COM14)`。

    Windows 下 `description` 就是设备管理器显示的友好名，但各驱动写法不一：
    多数已经自带 `(COM14)` 后缀，少数只有驱动名，个别虚拟串口两者相同，
    还有拿不到名字时 pyserial 给的 `n/a`。这里把这几种都规整成同一种写法。
    """
    device = str(getattr(info, "device", "") or "").strip()
    description = str(getattr(info, "description", "") or "").strip()
    if not device:
        return description or "未知端口"
    if not description or description.lower() in ("n/a", "none") or description.lower() == device.lower():
        return device
    # 友好名里已经带了 "(COM14)" 就不再补一次，免得出现 "... (COM14) (COM14)"
    if re.search(r"\(\s*" + re.escape(device) + r"\s*\)\s*$", description, re.IGNORECASE):
        return description
    return f"{description} ({device})"


def build_port_tooltip(info) -> str:
    """端口下拉框放不下长名字时的悬浮提示，顺带带上硬件 ID。"""
    lines = [format_port_label(info)]
    hwid = str(getattr(info, "hwid", "") or "").strip()
    if hwid and hwid.lower() not in ("n/a", "none"):
        lines.append(f"硬件 ID：{hwid}")
    return "\n".join(lines)


class SerialTab(QWidget):
    status_changed = Signal(str)

    def __init__(self, tab_name: str, theme: Theme = LIGHT_THEME):
        super().__init__()
        self.tab_name = tab_name
        self._theme = theme
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

    # -- 界面搭建 ---------------------------------------------------------

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        top_layout = QGridLayout()

        self.port_combo = QComboBox()
        # 下拉框被挤窄时，靠悬浮提示看完整端口名（提示内容见 refresh_ports）
        self.port_combo.currentIndexChanged.connect(self._sync_port_tooltip)

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
        self.encoding_combo.addItems(ENCODINGS)
        self.encoding_combo.setCurrentText("gbk")

        self.refresh_button = QPushButton("刷新串口")
        self.open_button = QPushButton("打开串口")

        top_layout.addWidget(QLabel("串口"), 0, 0)
        top_layout.addWidget(self.port_combo, 0, 1)
        top_layout.addWidget(self.refresh_button, 0, 2)
        top_layout.addWidget(QLabel("波特率"), 0, 3)
        top_layout.addWidget(self.baud_combo, 0, 4)
        top_layout.addWidget(QLabel("编码"), 0, 5)
        top_layout.addWidget(self.encoding_combo, 0, 6)

        top_layout.addWidget(QLabel("数据位"), 1, 0)
        top_layout.addWidget(self.data_bits_combo, 1, 1)
        top_layout.addWidget(QLabel("停止位"), 1, 2)
        top_layout.addWidget(self.stop_bits_combo, 1, 3)
        top_layout.addWidget(QLabel("校验位"), 1, 4)
        top_layout.addWidget(self.parity_combo, 1, 5)
        top_layout.addWidget(self.open_button, 1, 6)

        self.receive_area = QPlainTextEdit()
        self.receive_area.setObjectName("receiveArea")
        self.receive_area.setReadOnly(True)
        self.receive_area.setPlaceholderText("接收数据显示区域")

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
        self.toggle_command_panel_button.setMaximumWidth(110)

        # 面板默认只有 440px 宽，输入框和按钮挤在一行会把文字压成省略号，
        # 拆成「输入」和「操作」两行
        command_input_layout = QHBoxLayout()
        self.command_name_input = QLineEdit()
        self.command_name_input.setPlaceholderText("名称(可选)")
        self.command_name_input.setMaximumWidth(110)
        self.command_value_input = QLineEdit()
        self.command_value_input.setPlaceholderText("命令内容")
        command_input_layout.addWidget(self.command_name_input)
        command_input_layout.addWidget(self.command_value_input, 1)

        command_action_layout = QHBoxLayout()
        self.add_command_button = QPushButton("加入命令表")
        self.import_command_button = QPushButton("导入")
        self.remove_command_button = QPushButton("删除选中")
        self.send_command_button = QPushButton("发送选中")
        command_action_layout.addWidget(self.add_command_button)
        command_action_layout.addWidget(self.import_command_button)
        command_action_layout.addWidget(self.remove_command_button)
        command_action_layout.addStretch(1)
        command_action_layout.addWidget(self.send_command_button)

        self.command_table = QTableWidget(0, COMMAND_EDIT_COLUMN + 1)
        self.command_table.setHorizontalHeaderLabels(["名称", "命令内容", ""])
        header = self.command_table.horizontalHeader()
        header.setSectionResizeMode(COMMAND_NAME_COLUMN, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COMMAND_CONTENT_COLUMN, QHeaderView.Stretch)
        header.setSectionResizeMode(COMMAND_EDIT_COLUMN, QHeaderView.Fixed)
        self.command_table.setColumnWidth(COMMAND_EDIT_COLUMN, 32)
        self.command_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.command_table.setSelectionMode(QTableWidget.SingleSelection)
        self.command_table.setAlternatingRowColors(True)
        # 双击发送、点最右侧图标才进入编辑，所以不保留任何自动编辑触发器
        self.command_table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.command_panel = FloatingCommandPanel(self, self._theme)
        self.command_panel.body_layout().addLayout(command_input_layout)
        self.command_panel.body_layout().addLayout(command_action_layout)
        self.command_panel.body_layout().addWidget(self.command_table, 1)
        self.command_panel.setVisible(False)
        self.command_panel.close_button.clicked.connect(
            lambda: self.toggle_command_panel_button.setChecked(False)
        )
        self._command_panel_placed = False

        control_top_layout = QHBoxLayout()
        control_top_layout.setSpacing(14)
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

        self.rx_merge_combo = QComboBox()
        for label, merge_ms in RX_MERGE_OPTIONS.items():
            self.rx_merge_combo.addItem(label, merge_ms)
        self.rx_merge_combo.setCurrentText(DEFAULT_RX_MERGE_LABEL)
        self.rx_merge_combo.setToolTip(
            "间隔小于该值的数据会并成一条显示\n"
            "长报文就不会在中间插进时间戳、RX 前缀了"
        )

        self.clear_button = QPushButton("清空接收区")

        control_bottom_layout.addWidget(self.loop_send_checkbox)
        control_bottom_layout.addWidget(self.loop_interval_spin)
        control_bottom_layout.addSpacing(8)
        control_bottom_layout.addWidget(QLabel("合并"))
        control_bottom_layout.addWidget(self.rx_merge_combo)
        control_bottom_layout.addSpacing(8)
        control_bottom_layout.addWidget(QLabel("接收上限"))
        control_bottom_layout.addWidget(self.receive_limit_combo)
        control_bottom_layout.addSpacing(8)
        control_bottom_layout.addWidget(self.clear_button)
        control_bottom_layout.addStretch(1)

        log_file_layout = QHBoxLayout()
        self.log_to_file_checkbox = QCheckBox("实时写入TXT")
        self.log_file_path_input = QLineEdit()
        self.log_file_path_input.setPlaceholderText("选择TXT文件路径（追加写入）")
        self.select_log_file_button = QPushButton("选择文件")

        log_file_layout.addWidget(self.log_to_file_checkbox)
        log_file_layout.addWidget(self.log_file_path_input, 1)
        log_file_layout.addWidget(self.select_log_file_button)

        # 底部这些设置项平时要占三四行，收进一个可折叠容器
        self.settings_panel = QWidget()
        self.settings_panel.setObjectName("settingsPanel")
        settings_layout = QVBoxLayout(self.settings_panel)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(6)
        settings_layout.addLayout(control_top_layout)
        settings_layout.addLayout(control_bottom_layout)
        settings_layout.addLayout(log_file_layout)

        self.toggle_command_panel_button.setMaximumWidth(110)
        self.settings_toggle_button = QPushButton("设置 ▼")
        self.settings_toggle_button.setCheckable(True)
        self.settings_toggle_button.setChecked(True)
        self.settings_toggle_button.setMaximumWidth(90)
        self.settings_toggle_button.setToolTip("收起 / 展开下方的收发与日志设置")

        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(8)
        toolbar_layout.addWidget(self.toggle_command_panel_button)
        toolbar_layout.addWidget(self.settings_toggle_button)
        toolbar_layout.addStretch(1)

        # 日志记录状态要一眼看得到，单独做成带底色的指示标签
        self.log_status_label = QLabel()
        self.log_status_label.setObjectName("logStatusLabel")

        self.stats_label = QLabel("RX: 0 bytes | TX: 0 bytes | 未连接")
        self.stats_label.setObjectName("statsLabel")

        stats_layout = QHBoxLayout()
        stats_layout.addWidget(self.stats_label)
        stats_layout.addStretch(1)
        stats_layout.addWidget(self.log_status_label)

        root_layout.addLayout(top_layout)
        root_layout.addWidget(self.receive_area, 1)
        root_layout.addLayout(search_top_layout)
        root_layout.addLayout(search_bottom_layout)
        root_layout.addLayout(send_input_layout)
        root_layout.addLayout(toolbar_layout)
        root_layout.addWidget(self.settings_panel)
        root_layout.addLayout(stats_layout)

        # 日志状态指示的累计值与节流定时器
        self._log_lines_written = 0
        self._log_status_timer = QTimer(self)
        self._log_status_timer.setSingleShot(True)
        self._log_status_timer.setInterval(500)
        self._log_status_timer.timeout.connect(self._update_log_status)

        self._update_log_status()

        self.loop_timer = QTimer(self)
        self.loop_timer.setTimerType(Qt.CoarseTimer)

        # 自动滚动节流：高频数据下每包都滚一次会把 UI 拖死
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(16)
        self._scroll_timer.timeout.connect(self._scroll_to_bottom)

        # 接收合并缓冲：攒到出现空闲再作为一条输出
        self._rx_chunks: list = []
        self._rx_pending_bytes = 0
        self._rx_first_time: Optional[datetime] = None
        self._rx_merge_timer = QTimer(self)
        self._rx_merge_timer.setSingleShot(True)
        self._rx_merge_timer.timeout.connect(self._flush_rx_buffer)

        self.refresh_button.clicked.connect(self.refresh_ports)
        self.open_button.clicked.connect(self.toggle_connection)
        self.send_button.clicked.connect(self.send_data)
        self.clear_button.clicked.connect(self.clear_receive_area)
        self.loop_timer.timeout.connect(self._on_loop_send_tick)
        self.search_prev_button.clicked.connect(lambda: self.find_text(forward=False))
        self.search_next_button.clicked.connect(lambda: self.find_text(forward=True))
        self.search_input.returnPressed.connect(lambda: self.find_text(forward=True))
        self.highlight_button.clicked.connect(self.highlight_all_matches)
        self.clear_highlight_button.clicked.connect(self.clear_highlight)
        self.receive_limit_combo.currentIndexChanged.connect(self._trim_receive_area_to_limit)
        self.select_log_file_button.clicked.connect(self.select_log_file)
        self.toggle_command_panel_button.toggled.connect(self._toggle_command_panel)
        self.settings_toggle_button.toggled.connect(self._on_settings_toggled)
        self.add_command_button.clicked.connect(self.add_command_preset)
        self.import_command_button.clicked.connect(self.import_command_presets)
        self.remove_command_button.clicked.connect(self.remove_selected_command_preset)
        self.send_command_button.clicked.connect(self.send_selected_command_preset)

        connect_check_state(self.loop_send_checkbox, self._on_loop_send_changed)
        connect_check_state(self.log_to_file_checkbox, self._on_log_to_file_changed)
        # 定时发送执行中修改间隔要立刻生效，否则得先取消勾选再勾一次
        self.loop_interval_spin.valueChanged.connect(self._on_loop_interval_changed)

        self.command_table.cellDoubleClicked.connect(self._on_command_cell_double_clicked)
        self.command_table.cellChanged.connect(self._on_command_table_cell_changed)

    def apply_theme(self, theme: Theme) -> None:
        """切换主题时刷新本页需要单独处理的颜色。"""
        self._theme = theme
        self.command_panel.apply_theme(theme)
        if self.search_input.text().strip():
            self.highlight_all_matches(
                current_cursor=self.receive_area.textCursor(), force_focus=False
            )

    # -- 命令面板浮动定位 --------------------------------------------------

    def _toggle_command_panel(self, expanded: bool) -> None:
        if expanded:
            if not self._command_panel_placed:
                self._command_panel_placed = self._position_command_panel()
            self.command_panel.setVisible(True)
            self.command_panel.raise_()
        else:
            self.command_panel.setVisible(False)
        self.toggle_command_panel_button.setText("命令表 ▼" if expanded else "命令表 ▶")

    def _position_command_panel(self) -> bool:
        """按当前尺寸摆放命令面板。

        窗口首次显示前尺寸还是初始值，这时候算出来的位置会偏；返回 False
        让调用方别记为"已摆放"，等 resizeEvent 里尺寸就绪后再补一次。
        """
        if self.width() < 320 or self.height() < 320:
            return False
        self.command_panel.apply_default_geometry()
        return True

    def _clamp_command_panel(self) -> None:
        self.command_panel.clamp_into_parent()

    def resizeEvent(self, event) -> None:
        if self.command_panel.isVisible() and not self._command_panel_placed:
            self._command_panel_placed = self._position_command_panel()
        self._clamp_command_panel()
        super().resizeEvent(event)

    # -- 定时发送 ---------------------------------------------------------

    def _on_loop_send_changed(self, checked: bool) -> None:
        if checked:
            self.loop_timer.start(self.loop_interval_spin.value())
        else:
            self.loop_timer.stop()

    def _on_loop_interval_changed(self, value: int) -> None:
        if self.loop_send_checkbox.isChecked():
            self.loop_timer.start(value)

    def _on_loop_send_tick(self) -> None:
        """定时发送调用的是静默发送：串口没开就停下来，不要反复弹窗。"""
        text = self.send_input.text().strip()
        if not text:
            return
        if not self._send_text_payload(text, silent=True):
            self.loop_send_checkbox.setChecked(False)
            self.status_changed.emit(f"{self.tab_name} 定时发送已停止（串口未打开）")

    # -- 接收区容量控制 ----------------------------------------------------

    def _current_receive_limit_bytes(self) -> int:
        selected = self.receive_limit_combo.currentData()
        if isinstance(selected, int) and selected > 0:
            return selected
        return RECEIVE_LIMIT_OPTIONS["10MB"]

    def _trim_receive_area_to_limit(self) -> None:
        """超出上限时一次性砍掉前段内容。

        老实现逐块删除，10MB 上限下每次裁剪可能要执行几万次文档结构修改，
        界面会明显卡顿。这里改成按比例定位后一次删除，并顺手把字节计数重算，
        避免长期累加导致的偏差。
        """
        limit_bytes = self._current_receive_limit_bytes()
        if self._displayed_text_bytes <= limit_bytes:
            return

        doc = self.receive_area.document()
        if doc.blockCount() <= 1:
            self.receive_area.clear()
            self._displayed_text_bytes = 0
            return

        target_bytes = int(limit_bytes * TRIM_KEEP_RATIO)
        keep_chars = int(doc.characterCount() * (target_bytes / max(1, self._displayed_text_bytes)))
        keep_chars = max(1, min(keep_chars, doc.characterCount() - 1))

        self.receive_area.setUpdatesEnabled(False)
        try:
            cursor = QTextCursor(doc)
            cursor.setPosition(keep_chars)
            cursor.movePosition(QTextCursor.StartOfBlock)  # 不要从半行切断
            cursor.movePosition(QTextCursor.Start, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            self._displayed_text_bytes = len(
                self.receive_area.toPlainText().encode("utf-8", errors="replace")
            )
        finally:
            self.receive_area.setUpdatesEnabled(True)

    def _on_settings_toggled(self, expanded: bool) -> None:
        self.settings_panel.setVisible(expanded)
        self.settings_toggle_button.setText("设置 ▼" if expanded else "设置 ▶")

    # -- 日志文件 ---------------------------------------------------------

    def _update_log_status(self) -> None:
        """刷新日志记录状态指示。

        原来勾选后界面毫无反馈，用户没法确认到底有没有在记录，这里给一个
        带底色的常驻指示，并把累计写入行数也带上。
        """
        active = self.log_to_file_checkbox.isChecked()
        if active:
            path = self.log_file_path_input.text().strip()
            name = os.path.basename(path) if path else "(未选择文件)"
            self.log_status_label.setText(f"● 记录中 → {name}（{self._log_lines_written} 行）")
            state = "active"
        else:
            self.log_status_label.setText("○ 未记录到文件")
            state = "idle"

        if self.log_status_label.property("state") != state:
            self.log_status_label.setProperty("state", state)
            # 动态属性变化后必须重新 polish，否则 QSS 不会重算
            self.log_status_label.style().unpolish(self.log_status_label)
            self.log_status_label.style().polish(self.log_status_label)

    def _schedule_log_status_update(self) -> None:
        if not self._log_status_timer.isActive():
            self._log_status_timer.start()

    def select_log_file(self) -> None:
        current_path = self.log_file_path_input.text().strip()
        initial_dir = os.path.dirname(current_path) if current_path else os.path.expanduser("~")
        file_path, _ = QFileDialog.getSaveFileName(
            self, "选择日志文件（内容追加写入）", initial_dir, "Text Files (*.txt)"
        )
        if file_path:
            if not file_path.lower().endswith(".txt"):
                file_path += ".txt"
            self.log_file_path_input.setText(file_path)
            self._update_log_status()

    def _on_log_to_file_changed(self, checked: bool) -> None:
        if not checked:
            self._update_log_status()
            return

        path = self.log_file_path_input.text().strip()
        if not path:
            QMessageBox.warning(self, "提示", "请先选择TXT文件路径")
            # 取消勾选会再次回到本函数，状态指示随之回落
            self.log_to_file_checkbox.setChecked(False)
            return

        # 勾选时就验证一次可写，别等到有数据了才发现路径不可用
        try:
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(path, "a", encoding="utf-8"):
                pass
        except Exception as e:
            QMessageBox.critical(self, "日志文件不可写", str(e))
            self.log_to_file_checkbox.setChecked(False)
            return

        self._log_lines_written = 0
        self._update_log_status()
        self.status_changed.emit(f"{self.tab_name} 已开始记录到 {os.path.basename(path)}")

    def _append_rx_to_file(self, line: str) -> None:
        if not self.log_to_file_checkbox.isChecked():
            return

        file_path = self.log_file_path_input.text().strip()
        if not file_path:
            return

        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            self._txt_log_write_error_notified = False
            self._log_lines_written += 1
            self._schedule_log_status_update()
        except Exception as e:
            if not self._txt_log_write_error_notified:
                QMessageBox.critical(self, "写入日志失败", str(e))
                self._txt_log_write_error_notified = True
            self.log_to_file_checkbox.setChecked(False)

    # -- 命令表持久化 -----------------------------------------------------

    def _insert_command_row(self, name: str, content: str) -> None:
        row = self.command_table.rowCount()
        self.command_table.insertRow(row)
        self.command_table.setItem(row, COMMAND_NAME_COLUMN, QTableWidgetItem(name))
        self.command_table.setItem(row, COMMAND_CONTENT_COLUMN, QTableWidgetItem(content))

        edit_button = QPushButton("✎")
        edit_button.setObjectName("tableEditButton")
        edit_button.setToolTip("修改这条命令（双击整行是发送）")
        edit_button.setCursor(Qt.PointingHandCursor)
        edit_button.clicked.connect(
            lambda _checked=False, b=edit_button: self._begin_edit_command_row_by_button(b)
        )
        self.command_table.setCellWidget(row, COMMAND_EDIT_COLUMN, edit_button)

    def _collect_command_presets(self) -> list:
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
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(COMMANDS_STORE_PATH, "w", encoding="utf-8") as f:
                json.dump(commands, f, ensure_ascii=False, indent=2)
            self._commands_write_error_notified = False
        except Exception as e:
            if not self._commands_write_error_notified:
                QMessageBox.warning(self, "命令表保存失败", str(e))
                self._commands_write_error_notified = True

    def _normalize_command_lines(self, lines: list) -> list:
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
        store_path = COMMANDS_STORE_PATH

        # 从旧版本路径迁移一次，避免用户发现命令表"丢了"
        if not os.path.exists(store_path) and os.path.exists(LEGACY_COMMANDS_STORE_PATH):
            try:
                os.makedirs(CONFIG_DIR, exist_ok=True)
                os.replace(LEGACY_COMMANDS_STORE_PATH, store_path)
            except Exception:
                store_path = LEGACY_COMMANDS_STORE_PATH

        if not os.path.exists(store_path):
            self._load_default_command_presets()
            return

        try:
            with open(store_path, "r", encoding="utf-8") as f:
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

        lines: list = []
        try:
            if file_path.lower().endswith(".json"):
                data = json.loads(read_text_file(file_path))
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            lines.append(str(item.get("content", "")))
                        else:
                            lines.append(str(item))
            else:
                lines = read_text_file(file_path).splitlines()
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

    # -- 命令表交互 -------------------------------------------------------

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

    def _on_command_cell_double_clicked(self, row: int, col: int) -> None:
        """双击整行 = 发送；最右侧的编辑图标由按钮自己处理。"""
        if col == COMMAND_EDIT_COLUMN:
            return
        self.send_command_preset_by_row(row)

    # -- 行内编辑（由行尾的小图标触发）------------------------------------

    def _row_of_edit_button(self, button: QWidget) -> int:
        for row in range(self.command_table.rowCount()):
            if self.command_table.cellWidget(row, COMMAND_EDIT_COLUMN) is button:
                return row
        return -1

    def _begin_edit_command_row_by_button(self, button: QWidget) -> None:
        row = self._row_of_edit_button(button)
        if row >= 0:
            self._begin_edit_command_row(row)

    def _begin_edit_command_row(self, row: int) -> None:
        """让该行的名称单元格进入编辑，按 Tab 可以接着改命令内容。"""
        if row < 0 or row >= self.command_table.rowCount():
            return
        item = self.command_table.item(row, COMMAND_NAME_COLUMN)
        if item is None:
            return
        self.command_table.setCurrentCell(row, COMMAND_NAME_COLUMN)
        self.command_table.editItem(item)

    # -- 串口开关 ---------------------------------------------------------

    def refresh_ports(self) -> None:
        # 显示文本已经变成"友好名 (COM14)"，所以选中项要按 itemData 里的真实
        # 端口名恢复，不能再拿 currentText 去比对（那样永远匹配不上）。
        current = self.port_combo.currentData()
        self.port_combo.clear()
        for info in list_ports.comports():
            device = str(getattr(info, "device", "") or "").strip()
            if not device:
                continue
            self.port_combo.addItem(format_port_label(info), device)
            self.port_combo.setItemData(
                self.port_combo.count() - 1, build_port_tooltip(info), Qt.ToolTipRole
            )
        if self.port_combo.count() == 0:
            self.port_combo.setPlaceholderText("未检测到串口")
            self.port_combo.setToolTip("")
            return
        self.port_combo.setPlaceholderText("")
        # 设过占位文案之后，Qt 往空下拉框里 addItem 不会再自动选中第一项，
        # 这里显式选中：优先恢复原来的端口，否则选第一个。
        index = self.port_combo.findData(current) if current else -1
        self.port_combo.setCurrentIndex(index if index >= 0 else 0)
        # 索引没变时不会触发 currentIndexChanged，这里补一次保证提示是最新的
        self._sync_port_tooltip()

    def _sync_port_tooltip(self) -> None:
        """把当前项的悬浮提示同步到下拉框本身：分屏挤窄时靠它看完整名字。"""
        self.port_combo.setToolTip(str(self.port_combo.currentData(Qt.ToolTipRole) or ""))

    def selected_port(self) -> str:
        """下拉框里真正的端口名（COM14）——显示文本是友好名，不能拿去开串口。"""
        data = self.port_combo.currentData()
        if data:
            return str(data).strip()
        # 兜底：万一被外部塞进纯文本，就从 "友好名 (COM14)" 里抠出端口名
        text = self.port_combo.currentText().strip()
        match = re.search(r"\(([^()]+)\)\s*$", text)
        return (match.group(1) if match else text).strip()

    def get_config(self) -> SerialConfig:
        return SerialConfig(
            port=self.selected_port(),
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
        except (ValueError, KeyError):
            QMessageBox.critical(self, "参数错误", "波特率必须是数字")
            return

        if not cfg.port:
            QMessageBox.warning(self, "提示", "请先选择可用串口")
            return

        try:
            self.serial_port = serial.Serial(
                port=cfg.port,
                baudrate=cfg.baud_rate,
                bytesize=cfg.data_bits,
                stopbits=STOP_BITS[cfg.stop_bits_key],
                parity=cfg.parity,
                timeout=0.1,
                write_timeout=1.0,  # 防止底层写阻塞把 UI 卡死
            )

            self.reader_thread = SerialReadThread(self.serial_port)
            self.reader_thread.data_received.connect(self.on_data_received)
            self.reader_thread.error_occurred.connect(self.on_error)
            self.reader_thread.start()

            self.open_button.setText("关闭串口")
            self.update_stats("已连接")
            self.status_changed.emit(f"{self.tab_name} 已连接 {cfg.port}")
        except Exception as e:
            self.serial_port = None
            QMessageBox.critical(self, "打开串口失败", str(e))

    def close_port(self) -> None:
        if self.reader_thread:
            self.reader_thread.stop()
            if not self.reader_thread.wait(1000):
                # 线程没能及时退出（极端情况），先断开信号避免它再回写界面
                try:
                    self.reader_thread.data_received.disconnect()
                    self.reader_thread.error_occurred.disconnect()
                except Exception:
                    pass
            self.reader_thread = None

        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except Exception:
                pass

        self.serial_port = None
        self.loop_timer.stop()
        self.loop_send_checkbox.setChecked(False)
        self.open_button.setText("打开串口")
        self.update_stats("未连接")
        self.status_changed.emit(f"{self.tab_name} 已断开")

    def on_error(self, error: str) -> None:
        self.append_log(f"[错误] {error}")
        self.close_port()

    # -- 接收显示 ---------------------------------------------------------

    def append_log(self, text: str) -> None:
        self.receive_area.appendPlainText(text)
        self._displayed_text_bytes += len((text + "\n").encode("utf-8", errors="replace"))
        self._trim_receive_area_to_limit()

        if self.auto_scroll_checkbox.isChecked() and not self._scroll_timer.isActive():
            self._scroll_timer.start()

    def _scroll_to_bottom(self) -> None:
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

    def _current_rx_merge_ms(self) -> int:
        value = self.rx_merge_combo.currentData()
        return value if isinstance(value, int) else 0

    def on_data_received(self, data: bytes) -> None:
        self.rx_count += len(data)

        merge_ms = self._current_rx_merge_ms()
        if merge_ms <= 0:
            # 关闭合并：读到多少就显示多少
            self._emit_rx_line(data, datetime.now())
            return

        if not self._rx_chunks:
            self._rx_first_time = datetime.now()
        self._rx_chunks.append(data)
        self._rx_pending_bytes += len(data)

        if self._rx_pending_bytes >= RX_MERGE_MAX_BYTES:
            # 持续不断的流不会出现空闲，攒到上限就强制输出
            self._flush_rx_buffer()
            return

        # 每来一批就重置计时：只要数据还在陆续到达就继续攒
        self._rx_merge_timer.start(merge_ms)

    def _flush_rx_buffer(self) -> None:
        if not self._rx_chunks:
            return

        self._rx_merge_timer.stop()
        data = b"".join(self._rx_chunks)
        first_time = self._rx_first_time or datetime.now()
        self._rx_chunks.clear()
        self._rx_pending_bytes = 0
        self._rx_first_time = None

        self._emit_rx_line(data, first_time)

    def _emit_rx_line(self, data: bytes, when: datetime) -> None:
        """输出一条接收记录，时间戳取这批数据首个字节的到达时刻。"""
        body = self._format_rx_text(data)

        if self.timestamp_checkbox.isChecked():
            ts = when.strftime("%H:%M:%S.%f")[:-3]
            line = f"[{ts}] RX: {body}"
        else:
            line = body

        self.append_log(line)
        self._append_rx_to_file(line)
        self.update_stats("已连接")

    # -- 发送 -------------------------------------------------------------

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

    def _send_text_payload(self, text: str, silent: bool = False) -> bool:
        """发送数据。

        silent=True 时不在串口未打开/参数错误时弹窗，供定时发送使用。
        """
        if not text:
            return False

        if not self.serial_port or not self.serial_port.is_open:
            if not silent:
                QMessageBox.warning(self, "提示", "请先打开串口")
            return False

        try:
            payload = self._parse_send_payload(text)
        except ValueError as e:
            if not silent:
                QMessageBox.warning(self, "发送参数错误", str(e))
            return False

        if not payload:
            return False

        try:
            sent = self.serial_port.write(payload)
            self.tx_count += sent

            if self.timestamp_checkbox.isChecked():
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                tx_body = self._bytes_to_hex(payload) if self.hex_mode_checkbox.isChecked() else text
                self.append_log(f"[{ts}] TX: {tx_body}")

            self.update_stats("已连接")
            return True
        except Exception as e:
            if not silent:
                QMessageBox.critical(self, "发送失败", str(e))
            return False

    def send_data(self) -> None:
        text = self.send_input.text().strip()
        self._send_text_payload(text)

    # -- 搜索 / 高亮 ------------------------------------------------------

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
        normal_fmt.setBackground(QColor(self._theme.highlight_bg))
        normal_fmt.setForeground(QColor(self._theme.highlight_fg))

        current_fmt = QTextCharFormat()
        current_fmt.setBackground(QColor(self._theme.highlight_current_bg))
        current_fmt.setForeground(QColor(self._theme.highlight_current_fg))

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
        # 清空时把还没吐出来的合并缓冲一并丢掉，否则会立刻冒出来一行
        self._rx_merge_timer.stop()
        self._rx_chunks.clear()
        self._rx_pending_bytes = 0
        self._rx_first_time = None
        self.clear_highlight()

    def update_stats(self, status_text: str) -> None:
        self.stats_label.setText(f"RX: {self.rx_count} bytes | TX: {self.tx_count} bytes | {status_text}")

    def shutdown(self) -> None:
        self._scroll_timer.stop()
        self._log_status_timer.stop()
        self._rx_merge_timer.stop()
        self.loop_timer.stop()
        self.close_port()


# ---------------------------------------------------------------------------
# 6. 自定义标题栏 + 主窗口
# ---------------------------------------------------------------------------

class TitleBar(QWidget):
    """自定义标题栏。

    窗口去掉了系统边框，原来的顶部工具栏整体搬到这一行，
    同时由它承担窗口拖动、双击最大化，以及最小化/最大化/关闭三个按钮。
    """

    HEIGHT = 40

    def __init__(self, window: "MainWindow", theme: Theme = LIGHT_THEME) -> None:
        super().__init__(window)
        self._window = window
        self.setObjectName("titleBar")
        self.setFixedHeight(self.HEIGHT)
        self._drag_offset: Optional[QPoint] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 6, 0)
        layout.setSpacing(8)

        self.icon_label = QLabel()
        icon = QIcon(resource_path(os.path.join("assets", "app.ico")))
        if icon.isNull():
            self.icon_label.hide()
        else:
            self.icon_label.setPixmap(icon.pixmap(16, 16))
            self.icon_label.setFixedWidth(18)

        self.title_label = QLabel(APP_NAME)
        self.title_label.setObjectName("appTitle")
        self.title_label.setToolTip(f"{APP_NAME} v{APP_VERSION}")

        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.add_left_button = QPushButton("新增左侧标签")
        self.add_right_button = QPushButton("新增右侧标签")
        self.remove_left_button = QPushButton("关闭左侧当前")
        self.remove_right_button = QPushButton("关闭右侧当前")
        self.global_refresh_button = QPushButton("刷新全部串口")

        self.theme_label = QLabel("主题")
        self.theme_combo = QComboBox()
        self.theme_combo.setToolTip("切换界面配色")
        for t in THEME_LIST:
            self.theme_combo.addItem(t.label, t.key)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(theme.key)))

        self.minimize_button = QPushButton("─")
        self.maximize_button = QPushButton("□")
        self.close_button = QPushButton("✕")
        for btn in (self.minimize_button, self.maximize_button):
            btn.setObjectName("windowButton")
            btn.setFixedSize(44, 30)
            btn.setFocusPolicy(Qt.NoFocus)
        self.close_button.setObjectName("windowCloseButton")
        self.close_button.setFixedSize(44, 30)
        self.close_button.setFocusPolicy(Qt.NoFocus)
        self.set_maximized(False)

        # 除按钮外的一切都不接收鼠标事件，这样在空白、标题、状态文字上
        # 按住都能拖动窗口，落在按钮上的点击仍归按钮
        for w in (self.icon_label, self.title_label, self.status_label, self.theme_label):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        layout.addWidget(self.add_left_button)
        layout.addWidget(self.add_right_button)
        layout.addWidget(self.remove_left_button)
        layout.addWidget(self.remove_right_button)
        layout.addWidget(self.global_refresh_button)
        layout.addWidget(self.theme_label)
        layout.addWidget(self.theme_combo)
        layout.addSpacing(4)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button.clicked.connect(window.toggle_maximize)
        self.close_button.clicked.connect(window.close)

    def set_maximized(self, maximized: bool) -> None:
        self.maximize_button.setText("❐" if maximized else "□")
        self.maximize_button.setToolTip("向下还原" if maximized else "最大化")

    # -- 窗口拖动 ---------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and (event.buttons() & Qt.LeftButton):
            global_pos = event.globalPosition().toPoint()
            if self._window.is_custom_maximized():
                # 最大化状态下拖动：先还原，再让窗口跟着光标走
                self._window.restore_from_maximize(global_pos.x())
                self._drag_offset = QPoint(self._window.width() // 2, self.HEIGHT // 2)
            self._window.move(global_pos - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._window.toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, theme: Theme = LIGHT_THEME):
        super().__init__()
        self._theme = theme
        self.setWindowTitle(APP_NAME)
        # 自定义标题栏：去掉系统边框，把工具栏搬进标题栏那一行
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.resize(1280, 760)
        self.setMinimumSize(900, 580)
        self.tab_count = 0
        self._maximized = False
        self._normal_geometry: Optional[QRect] = None

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.title_bar = TitleBar(self, theme)
        # 转发控件引用，下面的信号连接与外部访问路径保持不变
        self.status_label = self.title_bar.status_label
        self.theme_combo = self.title_bar.theme_combo
        self.add_left_button = self.title_bar.add_left_button
        self.add_right_button = self.title_bar.add_right_button
        self.remove_left_button = self.title_bar.remove_left_button
        self.remove_right_button = self.title_bar.remove_right_button
        self.global_refresh_button = self.title_bar.global_refresh_button

        self.left_tabs = QTabWidget()
        self.right_tabs = QTabWidget()
        self.left_tabs.setTabsClosable(False)
        self.right_tabs.setTabsClosable(False)

        self.content_widget = QWidget()
        self.content_layout = QHBoxLayout(self.content_widget)
        # 标题栏占掉了顶部，内容区四周留内边距，否则控件会贴边
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_layout.setSpacing(8)
        self.content_layout.addWidget(self.left_tabs, 1)
        self.content_layout.addWidget(self.right_tabs, 1)

        layout.addWidget(self.title_bar)
        layout.addWidget(self.content_widget, 1)
        self.setCentralWidget(central)

        self.add_left_button.clicked.connect(lambda: self.add_serial_tab("left"))
        self.add_right_button.clicked.connect(lambda: self.add_serial_tab("right"))
        self.remove_left_button.clicked.connect(lambda: self.remove_current_tab("left"))
        self.remove_right_button.clicked.connect(lambda: self.remove_current_tab("right"))
        self.global_refresh_button.clicked.connect(self.refresh_all_ports)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_selected)

        self.add_serial_tab("left")

    # -- 窗口控制（无边框窗口需要自己实现）--------------------------------

    def is_custom_maximized(self) -> bool:
        return self._maximized

    def toggle_maximize(self) -> None:
        if self._maximized:
            self.restore_from_maximize()
            return

        self._normal_geometry = self.geometry()
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            # 用 availableGeometry 而不是 showMaximized()：无边框窗口直接最大化
            # 会把任务栏一起盖住
            self.setGeometry(screen.availableGeometry())
        self._maximized = True
        self.title_bar.set_maximized(True)

    def restore_from_maximize(self, follow_global_x: Optional[int] = None) -> None:
        """还原窗口。

        follow_global_x 用于"最大化状态下拖动标题栏"：还原的同时让窗口
        水平方向跟着光标走，符合 Windows 的操作直觉。
        """
        geo = self._normal_geometry if self._normal_geometry is not None else QRect(80, 80, 1280, 760)
        if follow_global_x is not None:
            geo.moveLeft(follow_global_x - geo.width() // 2)
            screen = self.screen() or QApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                geo.moveLeft(max(area.left(), min(geo.left(), area.right() - geo.width())))
        self.setGeometry(geo)
        self._maximized = False
        self.title_bar.set_maximized(False)

    def nativeEvent(self, eventType, message):
        """让无边框窗口恢复边缘拖拽缩放。

        FramelessWindowHint 的窗口在 Windows 上不再响应边缘缩放。这里拦截
        WM_NCHITTEST，把落在边缘若干像素内的命中结果换成对应缩放方向，
        其余位置原样交回 Qt，因此不会影响内部控件的正常点击。
        """
        if sys.platform == "win32" and not self._maximized:
            try:
                if bytes(eventType) == b"windows_generic_MSG":
                    msg = ctypes.wintypes.MSG.from_address(int(message))
                    if msg.message == WM_NCHITTEST:
                        hit = self._hit_test_resize(msg.lParam)
                        if hit is not None:
                            return True, hit
            except Exception:
                # 解析不了就退回默认行为，绝不能因为这个让窗口不可用
                pass
        return super().nativeEvent(eventType, message)

    def _hit_test_resize(self, l_param: int) -> Optional[int]:
        x = ctypes.c_short(l_param & 0xFFFF).value
        y = ctypes.c_short((l_param >> 16) & 0xFFFF).value
        pos = self.mapFromGlobal(QPoint(x, y))

        m = RESIZE_MARGIN
        on_left = pos.x() < m
        on_right = pos.x() > self.width() - m
        on_top = pos.y() < m
        on_bottom = pos.y() > self.height() - m

        if on_top and on_left:
            return HT_TOPLEFT
        if on_top and on_right:
            return HT_TOPRIGHT
        if on_bottom and on_left:
            return HT_BOTTOMLEFT
        if on_bottom and on_right:
            return HT_BOTTOMRIGHT
        if on_left:
            return HT_LEFT
        if on_right:
            return HT_RIGHT
        if on_top:
            return HT_TOP
        if on_bottom:
            return HT_BOTTOM
        return None

    # -- 主题 -------------------------------------------------------------

    def _on_theme_selected(self, _index: int) -> None:
        key = self.theme_combo.currentData()
        theme = THEMES.get(key)
        if theme is None or theme.key == self._theme.key:
            return

        self._theme = theme
        app = QApplication.instance()
        if app is not None:
            apply_global_theme(app, theme)
        for tab in self._iter_all_serial_tabs():
            tab.apply_theme(theme)
        save_config({"theme": key})
        self.status_label.setText(f"已切换到{theme.label}主题")

    # -- 标签页管理 -------------------------------------------------------

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
        tab = SerialTab(name, self._theme)
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


# ---------------------------------------------------------------------------
# 7. 程序入口
# ---------------------------------------------------------------------------

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SerialAssistant")
    app.setApplicationVersion(APP_VERSION)

    theme_key = str(load_config().get("theme", DEFAULT_THEME_KEY))
    theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME_KEY])
    apply_global_theme(app, theme)

    icon_path = resource_path(os.path.join("assets", "app.ico"))
    icon = QIcon(icon_path)
    if not icon.isNull():
        app.setWindowIcon(icon)

    window = MainWindow(theme)
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
