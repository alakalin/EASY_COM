using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;
using SerialAssistant.Models;
using SerialAssistant.Services;

namespace SerialAssistant;

/// <summary>
/// 悬浮命令面板：可拖动、可关闭、单击发送、双击修改。
/// 通过 Canvas 父容器定位（父级必须是 Canvas）。
/// </summary>
public partial class FloatingCommandPanel : UserControl
{
    public ObservableCollection<CommandItem> Commands { get; } = new();

    /// <summary>单击某条命令时触发，参数为命令内容。</summary>
    public event Action<string>? SendRequested;

    /// <summary>用户点击关闭按钮时触发。</summary>
    public event Action? CloseRequested;

    private readonly DispatcherTimer _clickTimer;
    private int _pendingRow = -1;
    private Point _dragOffset;
    private bool _dragging;

    [DllImport("user32.dll")]
    private static extern int GetDoubleClickTime();

    public FloatingCommandPanel()
    {
        InitializeComponent();
        CommandsGrid.ItemsSource = Commands;

        _clickTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromMilliseconds(GetDoubleClickTime())
        };
        _clickTimer.Tick += ClickTimer_Tick;

        CloseButton.Click += (_, _) => CloseRequested?.Invoke();
        AddButton.Click += AddButton_Click;
        ImportButton.Click += ImportButton_Click;
        RemoveButton.Click += RemoveButton_Click;
        SendSelButton.Click += SendSelButton_Click;
        CommandsGrid.CellEditEnding += (_, _) => CommandStore.Save(Commands);

        TitleBar.MouseLeftButtonDown += TitleBar_MouseLeftButtonDown;
        TitleBar.MouseLeftButtonUp += TitleBar_MouseLeftButtonUp;
        TitleBar.MouseMove += TitleBar_MouseMove;

        CommandsGrid.MouseLeftButtonDown += Grid_MouseLeftButtonDown;
        CommandsGrid.MouseDoubleClick += Grid_MouseDoubleClick;

        LoadCommands();
    }

    #region 命令数据

    public void LoadCommands()
    {
        Commands.Clear();
        foreach (var c in CommandStore.Load())
            Commands.Add(c);
    }

    private void AddButton_Click(object? sender, RoutedEventArgs e)
    {
        var content = (ContentBox.Text ?? "").Trim();
        if (string.IsNullOrEmpty(content))
            content = (ContentBox.Tag as string) ?? ""; // 忽略占位文本
        content = content.Trim();
        if (content is "命令内容" or "")
        {
            MessageBox.Show("请输入命令内容", "提示", MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        var name = (NameBox.Text ?? "").Trim();
        if (name is "名称" or "")
            name = $"命令{Commands.Count + 1}";

        Commands.Add(new CommandItem { Name = name, Content = content });
        CommandStore.Save(Commands);
        NameBox.Text = "名称";
        ContentBox.Text = "命令内容";
    }

    private void ImportButton_Click(object? sender, RoutedEventArgs e)
    {
        var dlg = new Microsoft.Win32.OpenFileDialog
        {
            Filter = "命令文件 (*.txt;*.json)|*.txt;*.json|文本文件 (*.txt)|*.txt|JSON (*.json)|*.json"
        };
        if (dlg.ShowDialog() != true)
            return;

        var lines = new List<string>();
        try
        {
            if (dlg.FileName.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
            {
                var data = JsonFileLoad(dlg.FileName);
                lines.AddRange(data);
            }
            else
            {
                lines.AddRange(File.ReadAllLines(dlg.FileName));
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show($"导入失败：{ex.Message}", "错误", MessageBoxButton.OK, MessageBoxImage.Error);
            return;
        }

        var normalized = Normalize(lines);
        if (normalized.Count == 0)
        {
            MessageBox.Show("未解析到有效命令", "提示", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        Commands.Clear();
        for (var i = 0; i < normalized.Count; i++)
            Commands.Add(new CommandItem { Name = $"导入{i + 1}", Content = normalized[i] });
        CommandStore.Save(Commands);
    }

    private void RemoveButton_Click(object? sender, RoutedEventArgs e)
    {
        var row = CommandsGrid.SelectedIndex;
        if (row < 0 || row >= Commands.Count)
        {
            MessageBox.Show("请先选中要删除的命令", "提示", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        Commands.RemoveAt(row);
        CommandStore.Save(Commands);
    }

    private void SendSelButton_Click(object? sender, RoutedEventArgs e)
    {
        var row = CommandsGrid.SelectedIndex;
        if (row < 0 || row >= Commands.Count)
        {
            MessageBox.Show("请先选中要发送的命令", "提示", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        SendRequested?.Invoke(Commands[row].Content);
    }

    private static List<string> JsonFileLoad(string path)
    {
        var text = File.ReadAllText(path);
        var data = System.Text.Json.JsonSerializer.Deserialize<List<CommandItem>>(text);
        var result = new List<string>();
        if (data is null)
            return result;
        foreach (var item in data)
            if (!string.IsNullOrWhiteSpace(item.Content))
                result.Add(item.Content);
        return result;
    }

    private static List<string> Normalize(IEnumerable<string> lines)
    {
        var result = new List<string>();
        foreach (var raw in lines)
        {
            var line = (raw ?? "").Trim();
            if (line.Length == 0)
                continue;
            if (line.StartsWith("#"))
                continue;
            result.Add(line);
        }

        return result;
    }

    #endregion

    #region 交互：单击发送 / 双击修改

    private void Grid_MouseLeftButtonDown(object? sender, MouseButtonEventArgs e)
    {
        var index = RowIndexFromPoint(e.OriginalSource);
        if (index < 0)
            return;
        _pendingRow = index;
        _clickTimer.Stop();
        _clickTimer.Start();
    }

    private void Grid_MouseDoubleClick(object? sender, MouseButtonEventArgs e)
    {
        // 取消单击触发的发送，进入默认的双击编辑
        _clickTimer.Stop();
        _pendingRow = -1;
    }

    private void ClickTimer_Tick(object? sender, EventArgs e)
    {
        _clickTimer.Stop();
        if (_pendingRow >= 0 && _pendingRow < Commands.Count)
            SendRequested?.Invoke(Commands[_pendingRow].Content);
        _pendingRow = -1;
    }

    private int RowIndexFromPoint(object? source)
    {
        var dep = source as DependencyObject;
        while (dep is not null && dep is not DataGridRow)
            dep = VisualTreeHelper.GetParent(dep);
        if (dep is DataGridRow row)
            return row.GetIndex();
        return -1;
    }

    #endregion

    #region 拖动

    private void TitleBar_MouseLeftButtonDown(object? sender, MouseButtonEventArgs e)
    {
        if (e.ChangedButton != MouseButton.Left)
            return;
        var canvas = Parent as Canvas;
        if (canvas is null)
            return;
        _dragging = true;
        TitleBar.CaptureMouse();
        _dragOffset = e.GetPosition(canvas);
        _dragStartLeft = Canvas.GetLeft(this);
        _dragStartTop = Canvas.GetTop(this);
        _dragStartMouse = e.GetPosition(canvas);
    }

    private double _dragStartLeft;
    private double _dragStartTop;
    private Point _dragStartMouse;

    private void TitleBar_MouseMove(object? sender, MouseEventArgs e)
    {
        if (!_dragging || e.LeftButton != MouseButtonState.Pressed)
            return;
        var canvas = Parent as Canvas;
        if (canvas is null)
            return;
        var pos = e.GetPosition(canvas);
        var left = _dragStartLeft + (pos.X - _dragStartMouse.X);
        var top = _dragStartTop + (pos.Y - _dragStartMouse.Y);
        left = Math.Max(0, Math.Min(left, canvas.ActualWidth - Width));
        top = Math.Max(0, Math.Min(top, canvas.ActualHeight - Height));
        Canvas.SetLeft(this, left);
        Canvas.SetTop(this, top);
    }

    private void TitleBar_MouseLeftButtonUp(object? sender, MouseButtonEventArgs e)
    {
        if (!_dragging)
            return;
        _dragging = false;
        TitleBar.ReleaseMouseCapture();
    }

    #endregion
}
