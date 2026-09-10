# 串口助手（Windows）

一个基于 `PySide6 + pyserial` 的 Windows 串口调试工具，支持多标签、多串口、时间戳、HEX 收发、关键字搜索与高亮，内置浅色/深色两套主题。

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
- 浅色 / 深色主题一键切换，选择自动记忆

## 主题

右上角「主题」下拉框可随时切换，切换后所有已打开的标签页立即重绘，
选择会写入 `~/.serial_assistant/config.json`，下次启动自动恢复。

主题由「调色板 + 全局样式表」两层构成（见 `main.py` 中的 `Theme` /
`build_palette` / `build_qss`），新增配色只需在 `THEME_LIST` 里加一个
`Theme` 实例。

> 注意：`QCheckBox::indicator` 的样式里不要使用 `data:` URI 的 SVG 图标，
> Qt 的样式表解析器会因此报错并丢弃整张样式表，勾选态用实心色块表达。

## 项目结构

- `main.py`：主程序入口
- `requirements.txt`：Python 依赖
- `SerialAssistant.spec`：PyInstaller 打包配置（onefile + 图标）
- `assets/app.png`：原始图标
- `assets/app.ico`：打包图标（由 png 转换）
- `screenshots/`：主题效果截图
- `.gitignore`：Git 忽略规则

## 用户数据

| 路径 | 内容 |
| --- | --- |
| `~/.serial_assistant/config.json` | 主题等偏好设置 |
| `~/.serial_assistant/commands.json` | 命令表内容 |

> 旧版本的 `~/.serial_assistant_commands.json` 会在首次启动时自动迁移。

## 本地开发运行

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
