# -*- coding: utf-8 -*-
"""生成 GPS 追踪设备 AT 指令集，供串口助手命令表导入。
输出:
  - gps_tracker_commands.json  (name + content, 直接可导入)
  - gps_tracker_commands.txt   (纯文本, 带 # 注释段落, 可直接导入)
"""
import json
import os

# (分类, 名称, 命令内容)
COMMANDS = [
    # ===== 电源 / 关机 =====
    ("电源关机", "PWRLIMIT 禁止关机(默认)", "PWRLIMIT,ON#"),
    ("电源关机", "PWRLIMIT 允许关机", "PWRLIMIT,OFF#"),
    ("电源关机", "PWRLIMIT 查询", "PWRLIMIT#"),
    ("电源关机", "SHUTDOWN 远程关机", "SHUTDOWN#"),
    ("电源关机", "FACTORY 恢复出厂设置", "FACTORY#"),
    ("电源关机", "RESET 重启", "RESET#"),

    # ===== 工作模式 =====
    ("工作模式", "MODE 定时定位模式", "MODE,1,300,0,1,1,0#"),
    ("工作模式", "MODE 运输模式", "MODE,4,20,10080,0,1,1,1#"),
    ("工作模式", "MODE 查询", "MODE#"),
    ("工作模式", "OFFLINE 进入假关机", "OFFLINE,ON#"),
    ("工作模式", "OFFLINE 退出假关机", "OFFLINE,OFF#"),
    ("工作模式", "OFFLINE 查询", "OFFLINE#"),

    # ===== 网络 / 服务器 =====
    ("网络服务器", "NETSET 仅GSM", "NETSET,0#"),
    ("网络服务器", "NETSET 仅4G", "NETSET,1#"),
    ("网络服务器", "NETSET 2G/4G自动(默认)", "NETSET,2#"),
    ("网络服务器", "NETSET 查询", "NETSET#"),
    ("网络服务器", "APN 设置", "APN,CMIOT,name,12345678#"),
    ("网络服务器", "APN 查询", "APN#"),
    ("网络服务器", "ASETAPN 自适应APN开启", "ASETAPN,ON#"),
    ("网络服务器", "ASETAPN 自适应APN关闭", "ASETAPN,OFF#"),
    ("网络服务器", "ASETAPN 查询", "ASETAPN#"),
    ("网络服务器", "GPRSON 开启(默认)", "GPRSON,ON#"),
    ("网络服务器", "GPRSON 关闭", "GPRSON,OFF#"),
    ("网络服务器", "GPRSON 查询", "GPRSON#"),
    ("网络服务器", "SERVER 设置(域名)", "SERVER,1,gpsdev.jimicloud.com,21102#"),
    ("网络服务器", "SERVER 设置(IP)", "SERVER,0,120.77.2.16,21102#"),
    ("网络服务器", "SERVER 查询", "SERVER#"),
    ("网络服务器", "SERVER,BACKUP 备用设置", "SERVER,BACKUP,1,gpsdev.tracksolidpro.com,21112#"),
    ("网络服务器", "SERVER,BACKUP 查询", "SERVER,BACKUP#"),
    ("网络服务器", "SERVER,CONN 仅连主域名(默认)", "SERVER,CONN,1#"),
    ("网络服务器", "SERVER,CONN 仅连备域名", "SERVER,CONN,2#"),
    ("网络服务器", "SERVER,CONN 查询", "SERVER,CONN#"),
    ("网络服务器", "SERVER2 AMS服务器设置", "SERVER2,1,ams.heytrack.com,12283#"),
    ("网络服务器", "SERVER2 查询", "SERVER2#"),
    ("网络服务器", "AMSCONN 连接次数限制", "AMSCONN,100#"),
    ("网络服务器", "AMSCONN 查询", "AMSCONN#"),
    ("网络服务器", "HBT 心跳间隔(默认5分)", "HBT,5#"),
    ("网络服务器", "HBT 查询", "HBT#"),
    ("网络服务器", "LOCKIP 域名锁定", "LOCKIP,ON#"),
    ("网络服务器", "LOCKIP 域名解锁(默认)", "LOCKIP,OFF#"),
    ("网络服务器", "LOCKIP 查询", "LOCKIP#"),

    # ===== 卡 / 标识查询 =====
    ("信息查询", "ICCID 查询", "ICCID#"),
    ("信息查询", "IMSI 查询", "IMSI#"),
    ("信息查询", "MULTIPLEIMSI 开启", "MULTIPLEIMSI,ON,20,50#"),
    ("信息查询", "MULTIPLEIMSI 关闭", "MULTIPLEIMSI,OFF#"),
    ("信息查询", "MULTIPLEIMSI 查询", "MULTIPLEIMSI#"),
    ("信息查询", "CHECK 自检", "CHECK#"),
    ("信息查询", "VERSION 版本查询", "VERSION#"),
    ("信息查询", "STATUS 状态查询", "STATUS#"),
    ("信息查询", "BMT 电量查询", "BMT#"),

    # ===== 报警 =====
    ("报警设置", "REMALM 防拆报警开启", "REMALM,ON,0#"),
    ("报警设置", "REMALM 防拆报警关闭", "REMALM,OFF#"),
    ("报警设置", "REMALM 查询", "REMALM#"),
    ("报警设置", "BATALM 低电报警开启", "BATALM,ON,0#"),
    ("报警设置", "BATALM 低电报警关闭", "BATALM,OFF#"),
    ("报警设置", "BATALM 查询", "BATALM#"),

    # ===== 温湿度 =====
    ("温湿度", "TEMPTIMER 上传间隔(默认20分)", "TEMPTIMER,20#"),
    ("温湿度", "TEMPTIMER 查询", "TEMPTIMER#"),
    ("温湿度", "TEMP 温湿度查询", "TEMP#"),
    ("温湿度", "TEMPALM 关闭报警", "TEMPALM,OFF,255,-18,255,80,0,0#"),
    ("温湿度", "TEMPALM 设置示例", "TEMPALM,ON,255,40,255,80,0,0#"),
    ("温湿度", "TEMPALM 查询", "TEMPALM#"),

    # ===== 蓝牙 =====
    ("蓝牙", "BTCONNECTALM 连接告警开启", "BTCONNECTALM,ON,0#"),
    ("蓝牙", "BTCONNECTALM 连接告警关闭", "BTCONNECTALM,OFF#"),
    ("蓝牙", "BTCONNECTALM 查询", "BTCONNECTALM#"),
    ("蓝牙", "DEVICEALM 外设告警开启", "DEVICEALM,BT,ON,0#"),
    ("蓝牙", "DEVICEALM 外设告警关闭", "DEVICEALM,BT,OFF#"),
    ("蓝牙", "DEVICEALM 查询", "DEVICEALM#"),
    ("蓝牙", "BT,MAC 本机MAC查询", "BT,MAC#"),
    ("蓝牙", "BT 扫描设置", "BT,SCANSET,30,30#"),
    ("蓝牙", "BT 扫描查询", "BT,SCANSET#"),
    ("蓝牙", "BT 白名单添加", "BT,PAIR,B4A8283A20E1#"),
    ("蓝牙", "BT 白名单清空", "BT,UNPAIR,ALL#"),
    ("蓝牙", "BT 白名单删除", "BT,UNPAIR,D5:A8:32:3C:46:B6#"),
    ("蓝牙", "BT 白名单查询", "BT,PAIR#"),
    ("蓝牙", "DOOR 外设识别开启", "DOOR,ON#"),
    ("蓝牙", "DOOR 外设识别关闭", "DOOR,OFF#"),
    ("蓝牙", "BLUETOOTH 广播开启(默认)", "BLUETOOTH,ON,5,2#"),
    ("蓝牙", "BLUETOOTH 广播关闭", "BLUETOOTH,OFF#"),
    ("蓝牙", "BLUETOOTH 查询", "BLUETOOTH#"),

    # ===== 号码 =====
    ("号码管理", "SOS 添加号码", "SOS,A,5656565,8988,#"),
    ("号码管理", "SOS 按序号删除", "SOS,D,1,2,3#"),
    ("号码管理", "SOS 按号码删除", "SOS,D,5656565#"),
    ("号码管理", "SOS 查询", "SOS#"),
    ("号码管理", "SOSPERMIT 权限设置", "SOSPERMIT,0,1#"),
    ("号码管理", "SOSPERMIT 查询", "SOSPERMIT#"),
    ("号码管理", "CENTER 中心号码添加", "CENTER,A,11223344#"),
    ("号码管理", "CENTER 中心号码删除", "CENTER,D,11223344#"),
    ("号码管理", "CENTER 查询", "CENTER#"),
    ("号码管理", "PERMIT 中心号码权限", "PERMIT,0#"),
    ("号码管理", "PERMIT 查询", "PERMIT#"),

    # ===== 时区 =====
    ("时区", "ASETGMT 时区自适应开启", "ASETGMT,ON#"),
    ("时区", "ASETGMT 时区自适应关闭", "ASETGMT,OFF#"),
    ("时区", "ASETGMT 查询", "ASETGMT#"),
    ("时区", "GMT 手动设置东8区", "GMT,E,8,0#"),
    ("时区", "GMT 查询", "GMT#"),
]

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- JSON (name + content) ----
json_obj = []
for cat, name, content in COMMANDS:
    json_obj.append({"category": cat, "name": name, "content": content})

json_path = os.path.join(OUT_DIR, "gps_tracker_commands.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(json_obj, f, ensure_ascii=False, indent=2)

# ---- TXT (纯文本, 带 # 注释分段) ----
txt_path = os.path.join(OUT_DIR, "gps_tracker_commands.txt")
lines = ["# GPS追踪设备 AT 指令集 (每行一条, 以#开头的注释行导入时自动忽略)", ""]
cur_cat = None
for cat, name, content in COMMANDS:
    if cat != cur_cat:
        cur_cat = cat
        lines.append(f"# === {cat} ===")
    lines.append(f"# {name}")
    lines.append(content)
lines.append("")
with open(txt_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

PREFIX = "AT^GT_CM=CMD,"

# ---- 带前缀 JSON (name + content) ----
json_prefixed = []
for cat, name, content in COMMANDS:
    json_prefixed.append({
        "category": cat,
        "name": name,
        "content": PREFIX + content,
    })
json_prefixed_path = os.path.join(OUT_DIR, "gps_tracker_commands_at.json")
with open(json_prefixed_path, "w", encoding="utf-8") as f:
    json.dump(json_prefixed, f, ensure_ascii=False, indent=2)

# ---- 带前缀 TXT ----
txt_prefixed_path = os.path.join(OUT_DIR, "gps_tracker_commands_at.txt")
plines = ["# GPS追踪设备 AT 指令集 (每条带 AT^GT_CM=CMD, 前缀)", ""]
cur_cat = None
for cat, name, content in COMMANDS:
    if cat != cur_cat:
        cur_cat = cat
        plines.append(f"# === {cat} ===")
    plines.append(f"# {name}")
    plines.append(PREFIX + content)
plines.append("")
with open(txt_prefixed_path, "w", encoding="utf-8") as f:
    f.write("\n".join(plines))

print(f"JSON: {json_path}  ({len(json_obj)} 条)")
print(f"TXT : {txt_path}  ({len(COMMANDS)} 条)")
print(f"JSON(AT): {json_prefixed_path}  ({len(json_prefixed)} 条)")
print(f"TXT(AT) : {txt_prefixed_path}  ({len(COMMANDS)} 条)")
