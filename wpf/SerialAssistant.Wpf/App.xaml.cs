using System;
using System.IO;
using System.Text;
using System.Windows;

namespace SerialAssistant;

public partial class App : Application
{
    static App()
    {
        // .NET Core/.NET 5+ 默认不自带 GBK/GB2312/Big5 等中文编码页，必须显式注册。
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
    }

    protected override void OnStartup(StartupEventArgs e)
    {
        DispatcherUnhandledException += OnDispatcherUnhandled;
        AppDomain.CurrentDomain.UnhandledException += OnDomainUnhandled;
        base.OnStartup(e);
    }

    private void OnDispatcherUnhandled(object sender, System.Windows.Threading.DispatcherUnhandledExceptionEventArgs e)
    {
        Dump(e.Exception, "DispatcherUnhandledException");
        e.Handled = true;
    }

    private void OnDomainUnhandled(object sender, System.UnhandledExceptionEventArgs e)
    {
        Dump(e.ExceptionObject as Exception, "AppDomain.UnhandledException");
    }

    private static void Dump(Exception? ex, string kind)
    {
        var text = $"[{kind}] {DateTime.Now:yyyy-MM-dd HH:mm:ss}\n{ex}";
        try
        {
            var path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Desktop), "SA_crash.log");
            File.WriteAllText(path, text);
        }
        catch { }
        MessageBox.Show(text, "串口助手启动失败");
    }
}
