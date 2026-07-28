using System;
using System.IO.Ports;
using System.Text;

namespace SerialAssistant.Services;

/// <summary>
/// 串口封装：在后台线程接收数据，通过事件回调给 UI。
/// </summary>
public class SerialService : IDisposable
{
    private SerialPort? _port;

    public event Action<byte[]>? DataReceived;
    public event Action<string>? ErrorOccurred;

    public bool IsOpen => _port?.IsOpen ?? false;

    // 配置（在 Open 前设置）
    public string PortName { get; set; } = "";
    public int BaudRate { get; set; } = 115200;
    public int DataBits { get; set; } = 8;
    public StopBits StopBits { get; set; } = StopBits.One;
    public Parity Parity { get; set; } = Parity.None;
    public Encoding Encoding { get; set; } = Encoding.GetEncoding("GBK");

    public void Open()
    {
        Close();
        _port = new SerialPort(PortName, BaudRate, Parity, DataBits, StopBits)
        {
            ReadTimeout = 200,
            WriteTimeout = 500
        };
        _port.DataReceived += OnDataReceived;
        _port.ErrorReceived += OnErrorReceived;
        _port.Open();
    }

    public void Send(byte[] data)
    {
        if (_port is not { IsOpen: true })
            throw new InvalidOperationException("串口未打开");
        _port.Write(data, 0, data.Length);
    }

    public void Close()
    {
        if (_port is null)
            return;
        _port.DataReceived -= OnDataReceived;
        _port.ErrorReceived -= OnErrorReceived;
        try
        {
            if (_port.IsOpen)
                _port.Close();
        }
        catch
        {
            // 忽略关闭异常
        }

        _port.Dispose();
        _port = null;
    }

    private void OnDataReceived(object sender, SerialDataReceivedEventArgs e)
    {
        if (_port is null || !_port.IsOpen)
            return;
        try
        {
            var buffer = new byte[_port.BytesToRead];
            var read = _port.Read(buffer, 0, buffer.Length);
            if (read <= 0)
                return;
            var data = read == buffer.Length ? buffer : buffer[..read];
            DataReceived?.Invoke(data);
        }
        catch (Exception ex)
        {
            ErrorOccurred?.Invoke(ex.Message);
        }
    }

    private void OnErrorReceived(object sender, SerialErrorReceivedEventArgs e)
    {
        ErrorOccurred?.Invoke(e.EventType.ToString());
    }

    public void Dispose() => Close();
}
