namespace SerialAssistant.Models;

/// <summary>
/// 命令预设：名称 + 命令内容。
/// </summary>
public class CommandItem
{
    public string Name { get; set; } = string.Empty;
    public string Content { get; set; } = string.Empty;
}
