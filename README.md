# 简约串口助手 v3.0.0（Windows）

一个基于 `PySide6 + pyserial` 的 Windows 串口调试工具，支持多标签、多串口、时间戳、HEX 收发、关键字搜索与高亮，内置**浅色 / 深色 / 绿色**三套主题，默认绿色。

## 功能特性

- 串口参数配置：端口、波特率、数据位、停止位、校验位
- 多标签连接串口：单标签全屏、双标签左右并行
- 文本/HEX 收发模式切换
- 接收/发送时间戳显示（毫秒）
- 中文编码支持（默认 `gbk`，可切 `gb18030` / `utf-8`）
- 接收区关键字搜索（上一个/下一个）、关键字高亮与清除高亮
- 接收上限可选（512KB / 1MB / 10MB / 40MB），超限自动裁剪前段
- 定时发送（间隔运行中可即时调整）、自动滚动开关
- 接收内容实时追加写入 TXT
- 悬浮命令表：可拖动、单击发送、双击修改，支持导入 `.txt` / `.json`
- 浅色 / 深色 / 绿色主题一键切换，选择自动记忆
- 无边框窗口：工具栏合并进标题栏，支持拖动、双击最大化与边缘缩放

## 主题

标题栏右侧「主题」下拉框可随时切换（浅色 / 深色 / 绿色），切换后所有已打开
的标签页立即重绘，选择写入 `~/.serial_assistant/config.json`，下次启动自动
恢复。**默认使用绿色主题。**

三套主题的色值全部对齐 [Radix Colors](https://www.radix-ui.com/colors) 色阶，
代码里每个值都标注了对应色阶编号（如 `# green-2`），微调时按编号定位。
色阶语义：`1` 应用背景 / `2` 次级背景 / `3` 控件背景 / `4` hover / `5` active /
`6` 边框 / `9` 实心主色 / `11` 低对比文字 / `12` 高对比文字。

主题由「调色板 + 全局样式表」两层构成（见 `main.py` 中的 `Theme` /
`build_palette` / `build_qss`），新增配色只需在 `THEME_LIST` 里加一个
`Theme` 实例。

两个容易踩的点：

- `accent` 与 `accent_text` 必须分开取值。前者用于实心填充，后者用于文字，
  深色模式下两者的合适亮度并不相同，共用一个值会导致文字对比度不足。
- `QCheckBox::indicator` 的样式里不要使用 `data:` URI 的 SVG 图标，Qt 的
  样式表解析器会因此报错并**丢弃整张样式表**，勾选态用实心色块表达。

## 项目结构

- `main.py`：主程序（单文件，含主题系统、串口线程、自定义标题栏、界面）
- `requirements.txt`：Python 依赖
- `assets/app.ico`：程序图标
- `screenshots/`：主题与界面效果截图
- `SerialAssistant*.spec`：PyInstaller 打包配置
- `build_gps_commands.py`、`gps_tracker_commands*`：GPS 指令集与生成脚本
- `.gitignore`：Git 忽略规则

## 用户数据

| 路径 | 内容 |
| --- | --- |
| `~/.serial_assistant/config.json` | 主题等偏好设置 |
| `~/.serial_assistant/commands.json` | 命令表内容 |

> 旧版本的 `~/.serial_assistant_commands.json` 会在首次启动时自动迁移。

## 运行

Windows 下双击桌面快捷方式「简约串口助手」即可启动（快捷方式指向
`pythonw.exe` + `main.py`，不会弹出控制台窗口）。

也可以命令行运行：

```bash
pip install -r requirements.txt
python main.py
```

## 打包（onefile）

已在 `SerialAssistant.spec` 中配置：
- 产物名：`SerialAssistant_onefile.exe`
- 图标：`assets/app.ico`
- 模式：`onefile`

执行打包：

```bash
pyinstaller --noconfirm --clean SerialAssistant.spec
```

打包产物：

- `dist/SerialAssistant_onefile.exe`


## 环境信息

- Python 3.11
- PySide6 6.9.1
- pyserial 3.5
- PyInstaller 6.19.0
