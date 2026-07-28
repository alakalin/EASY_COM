using System;
using System.IO;
using System.IO.Ports;
using System.Linq;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Threading;
using SerialAssistant.Services;

namespace SerialAssistant;

public partial class SerialSessionView : UserControl
{
    private readonly SerialService _serial = new();
    private readonly DispatcherTimer _loopTimer = new() { Interval = TimeSpan.FromMilliseconds(1000) };

    private long _rxBytes;
    private long _txBytes;
    private FloatingCommandPanel? _panel;
    private bool _panelPositioned;

    public SerialSessionView()
    {
        InitializeComponent();
        InitCombos();
        RefreshPorts();

        _serial.DataReceived += OnDataReceived;
        _serial.ErrorOccurred += msg => Dispatcher.Invoke(() => MessageBox.Show(msg, "串口错误"));

        RefreshButton.Click += (_, _) => RefreshPorts();
        OpenButton.Click += OpenButton_Click;
        SendButton.Click += (_, _) => SendText(SendBox.Text);
        SearchPrev.Click += (_, _) => FindNext(false);
        SearchNext.Click += (_, _) => FindNext(true);
        HighlightAll.Click += (_, _) => FindNext(true);
        ClearHighlight.Click += (_, _) => ReceiveBox.Select(0, 0);
        ClearButton.Click += (_, _) => { ReceiveBox.Clear(); };
        SelectLogFileButton.Click += SelectLogFile;
        LoopCheck.Checked += LoopCheck_Changed;
        LoopCheck.Unchecked += LoopCheck_Changed;
        _loopTimer.Tick += (_, _) => SendText(SendBox.Text);

        SetupFloatingPanel();
    }

    #region 初始化

    private void InitCombos()
    {
        BaudCombo.Items.Add("1200"); BaudCombo.Items.Add("2400"); BaudCombo.Items.Add("4800");
        BaudCombo.Items.Add("9600"); BaudCombo.Items.Add("19200"); BaudCombo.Items.Add("38400");
        BaudCombo.Items.Add("57600"); BaudCombo.Items.Add("115200"); BaudCombo.Items.Add("230400");
        BaudCombo.Items.Add("460800"); BaudCombo.Items.Add("921600");
        BaudCombo.Text = "115200";

        DataBitsCombo.Items.Add("5"); DataBitsCombo.Items.Add("6");
        DataBitsCombo.Items.Add("7"); DataBitsCombo.Items.Add("8");
        DataBitsCombo.Text = "8";

        StopBitsCombo.Items.Add("1"); StopBitsCombo.Items.Add("1.5"); StopBitsCombo.Items.Add("2");
        StopBitsCombo.Text = "1";

        ParityCombo.Items.Add("None"); ParityCombo.Items.Add("Odd"); ParityCombo.Items.Add("Even");
        ParityCombo.Text = "None";

        EncodingCombo.Items.Add("gbk"); EncodingCombo.Items.Add("gb18030"); EncodingCombo.Items.Add("utf-8");
        EncodingCombo.Text = "gbk";

        LimitCombo.Items.Add("512KB"); LimitCombo.Items.Add("1MB");
        LimitCombo.Items.Add("10MB"); LimitCombo.Items.Add("40MB");
        LimitCombo.Text = "10MB";
    }

    public void RefreshPorts()
    {
        var current = PortCombo.Text;
        PortCombo.Items.Clear();
        foreach (var p in SerialPort.GetPortNames())
            PortCombo.Items.Add(p);
        if (!string.IsNullOrEmpty(current) && PortCombo.Items.Contains(current))
            PortCombo.Text = current;
    }

    #endregion

    #region 悬浮命令面板

    private void SetupFloatingPanel()
    {
        _panel = new FloatingCommandPanel();
        OverlayCanvas.Children.Add(_panel);
        _panel.Visibility = Visibility.Collapsed;
        _panel.SendRequested += content => SendText(content);
        _panel.CloseRequested += () => ToggleCommandButton.IsChecked = false;

        ToggleCommandButton.Checked += (_, _) => ShowPanel();
        ToggleCommandButton.Unchecked += (_, _) => { if (_panel is not null) _panel.Visibility = Visibility.Collapsed; };
    }

    private void ShowPanel()
    {
        if (_panel is null)
            return;
        if (!_panelPositioned)
        {
            var left = Math.Max(12, OverlayCanvas.ActualWidth - _panel.Width - 12);
            CanvasSetLeftSafe(left);
            System.Windows.Controls.Canvas.SetTop(_panel, 12);
            _panelPositioned = true;
        }

        _panel.Visibility = Visibility.Visible;
    }

    private void CanvasSetLeftSafe(double left)
    {
        if (_panel is not null)
            System.Windows.Controls.Canvas.SetLeft(_panel, left);
    }

    #endregion

    #region 串口开关

    private void OpenButton_Click(object? sender, RoutedEventArgs e)
    {
        if (_serial.IsOpen)
        {
            _serial.Close();
            OpenButton.Content = "打开串口";
            UpdateStats("未连接");
            return;
        }

        if (string.IsNullOrWhiteSpace(PortCombo.Text))
        {
            MessageBox.Show("请先选择可用串口", "提示", MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        _serial.PortName = PortCombo.Text.Trim();
        try
        {
            _serial.BaudRate = int.Parse(BaudCombo.Text.Trim());
        }
        catch
        {
            MessageBox.Show("波特率必须是数字", "参数错误", MessageBoxButton.OK, MessageBoxImage.Error);
            return;
        }

        _serial.DataBits = int.Parse(DataBitsCombo.Text);
        _serial.StopBits = MapStopBits(StopBitsCombo.Text);
        _serial.Parity = MapParity(ParityCombo.Text);
        _serial.Encoding = CurrentEncoding;

        try
        {
            _serial.Open();
            OpenButton.Content = "关闭串口";
            UpdateStats("已连接");
        }
        catch (Exception ex)
        {
            MessageBox.Show($"打开串口失败：{ex.Message}", "错误", MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }

    private static StopBits MapStopBits(string s) => s switch
    {
        "1.5" => StopBits.OnePointFive,
        "2" => StopBits.Two,
        _ => StopBits.One
    };

    private static Parity MapParity(string s) => s switch
    {
        "Odd" => Parity.Odd,
        "Even" => Parity.Even,
        _ => Parity.None
    };

    private Encoding CurrentEncoding
    {
        get
        {
            try
            {
                return Encoding.GetEncoding(EncodingCombo.Text.Trim());
            }
            catch
            {
                return Encoding.GetEncoding("GBK");
            }
        }
    }

    #endregion

    #region 收发

    private void OnDataReceived(byte[] data)
    {
        Dispatcher.Invoke(() => AppendReceived(data));
    }

    private void AppendReceived(byte[] data)
    {
        _rxBytes += data.Length;
        var body = HexCheck.IsChecked == true ? Hex(data) : CurrentEncoding.GetString(data);
        var line = TimestampCheck.IsChecked == true
            ? $"[{DateTime.Now:HH:mm:ss.fff}] RX: {body}\n"
            : body;

        ReceiveBox.AppendText(line);
        if (AutoScrollCheck.IsChecked == true)
            ReceiveBox.ScrollToEnd();

        TrimReceive();

        if (LogCheck.IsChecked == true && !string.IsNullOrWhiteSpace(LogPathBox.Text))
        {
            try
            {
                File.AppendAllText(LogPathBox.Text, line);
            }
            catch
            {
                // 忽略写日志失败
            }
        }

        UpdateStats("已连接");
    }

    private void TrimReceive()
    {
        var limit = CurrentLimitBytes();
        if (limit <= 0)
            return;
        var len = ReceiveBox.Text.Length;
        if (len > limit)
            ReceiveBox.Text = ReceiveBox.Text.Substring(len - (int)limit);
    }

    private long CurrentLimitBytes() => LimitCombo.Text switch
    {
        "512KB" => 512 * 1024,
        "1MB" => 1024 * 1024,
        "10MB" => 10 * 1024 * 1024,
        "40MB" => 40 * 1024 * 1024,
        _ => 10 * 1024 * 1024
    };

    private bool SendText(string? text)
    {
        if (string.IsNullOrEmpty(text))
            return false;
        if (!_serial.IsOpen)
        {
            MessageBox.Show("请先打开串口", "提示", MessageBoxButton.OK, MessageBoxImage.Warning);
            return false;
        }

        byte[] payload;
        try
        {
            payload = BuildPayload(text);
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "发送参数错误", MessageBoxButton.OK, MessageBoxImage.Warning);
            return false;
        }

        if (payload.Length == 0)
            return false;

        try
        {
            _serial.Send(payload);
            _txBytes += payload.Length;
            if (TimestampCheck.IsChecked == true)
            {
                var shown = HexCheck.IsChecked == true ? Hex(payload) : text;
                ReceiveBox.AppendText($"[{DateTime.Now:HH:mm:ss.fff}] TX: {shown}\n");
                if (AutoScrollCheck.IsChecked == true)
                    ReceiveBox.ScrollToEnd();
            }

            UpdateStats("已连接");
            return true;
        }
        catch (Exception ex)
        {
            MessageBox.Show($"发送失败：{ex.Message}", "错误", MessageBoxButton.OK, MessageBoxImage.Error);
            return false;
        }
    }

    private byte[] BuildPayload(string text)
    {
        if (HexCheck.IsChecked == true)
        {
            var norm = System.Text.RegularExpressions.Regex.Replace(text.Trim(), @"\s+", " ");
            if (norm.Length == 0)
                return Array.Empty<byte>();
            var bytes = Convert.FromHexString(norm);
            if (NewlineCheck.IsChecked == true)
                return bytes.Concat(new byte[] { 0x0D, 0x0A }).ToArray();
            return bytes;
        }

        var s = text;
        if (NewlineCheck.IsChecked == true)
            s += "\r\n";
        return CurrentEncoding.GetBytes(s);
    }

    #endregion

    #region 搜索

    private void FindNext(bool forward)
    {
        var word = SearchBox.Text;
        if (string.IsNullOrEmpty(word))
            return;
        var text = ReceiveBox.Text;
        if (string.IsNullOrEmpty(text))
            return;

        int idx;
        if (forward)
        {
            idx = text.IndexOf(word, ReceiveBox.SelectionStart + ReceiveBox.SelectionLength, StringComparison.OrdinalIgnoreCase);
            if (idx < 0)
                idx = text.IndexOf(word, 0, StringComparison.OrdinalIgnoreCase);
        }
        else
        {
            idx = text.LastIndexOf(word, Math.Max(0, ReceiveBox.SelectionStart - 1), StringComparison.OrdinalIgnoreCase);
            if (idx < 0)
                idx = text.LastIndexOf(word, text.Length - 1, StringComparison.OrdinalIgnoreCase);
        }

        if (idx >= 0)
        {
            ReceiveBox.Focus();
            ReceiveBox.Select(idx, word.Length);
            ReceiveBox.ScrollToLine(ReceiveBox.GetLineIndexFromCharacterIndex(idx));
        }
    }

    #endregion

    #region 循环发送 / 日志

    private void LoopCheck_Changed(object? sender, RoutedEventArgs e)
    {
        if (LoopCheck.IsChecked == true)
        {
            if (!int.TryParse(LoopIntervalBox.Text, out var ms) || ms < 10)
                ms = 1000;
            _loopTimer.Interval = TimeSpan.FromMilliseconds(ms);
            _loopTimer.Start();
        }
        else
        {
            _loopTimer.Stop();
        }
    }

    private void SelectLogFile(object? sender, RoutedEventArgs e)
    {
        var dlg = new Microsoft.Win32.SaveFileDialog
        {
            Filter = "Text Files (*.txt)|*.txt",
            FileName = "serial_log.txt"
        };
        if (dlg.ShowDialog() == true)
            LogPathBox.Text = dlg.FileName;
    }

    #endregion

    private void UpdateStats(string status)
    {
        StatsLabel.Content = $"RX: {_rxBytes} bytes | TX: {_txBytes} bytes | {status}";
    }

    private static string Hex(byte[] data) =>
        string.Join(" ", System.Array.ConvertAll(data, b => b.ToString("X2")));
}
