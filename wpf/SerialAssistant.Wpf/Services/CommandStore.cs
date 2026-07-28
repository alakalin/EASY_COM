using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Windows;
using SerialAssistant.Models;

namespace SerialAssistant.Services;

/// <summary>
/// 命令预设的 JSON 持久化（存放于用户目录）。
/// </summary>
public static class CommandStore
{
    private static readonly string StorePath =
        Path.Combine(System.Environment.GetFolderPath(System.Environment.SpecialFolder.UserProfile),
            ".serial_assistant_commands.json");

    public static List<CommandItem> Load()
    {
        if (!File.Exists(StorePath))
            return DefaultCommands();

        try
        {
            var json = File.ReadAllText(StorePath);
            var data = JsonSerializer.Deserialize<List<CommandItem>>(json);
            if (data is { Count: > 0 })
                return data;
        }
        catch
        {
            // 损坏则回退默认
        }

        return DefaultCommands();
    }

    public static void Save(IEnumerable<CommandItem> commands)
    {
        try
        {
            var json = JsonSerializer.Serialize(commands,
                new JsonSerializerOptions { WriteIndented = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
            File.WriteAllText(StorePath, json);
        }
        catch
        {
            // 忽略保存失败
        }
    }

    public static List<CommandItem> DefaultCommands()
    {
        var lines = new[]
        {
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
            "AT^GT_CM=PCBA,MCU,LIGHT",
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
            "AT^GT_CM=PCBA,MCU,SHUTDOWN"
        };

        var list = new List<CommandItem>();
        for (var i = 0; i < lines.Length; i++)
            list.Add(new CommandItem { Name = $"默认{i + 1}", Content = lines[i] });
        return list;
    }
}
