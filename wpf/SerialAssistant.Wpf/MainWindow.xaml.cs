using System.Windows;
using System.Windows.Controls;

namespace SerialAssistant;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();

        SplitButton.Click += (_, _) => ApplySplitLayout();
        CloseRightButton.Click += (_, _) =>
        {
            SplitButton.IsChecked = false;
            ApplySplitLayout();
        };
        RefreshAllButton.Click += (_, _) =>
        {
            LeftSession.RefreshPorts();
            RightSession.RefreshPorts();
        };

        ApplySplitLayout();
    }

    /// <summary>
    /// 根据「分屏」开关决定右栏是否显示，并调整左右列宽。
    /// 开启：左右各占一半，中间分隔条可见，可拖拽调整。
    /// 关闭：只显示左栏，占满整个宽度。
    /// </summary>
    private void ApplySplitLayout()
    {
        bool split = SplitButton.IsChecked == true;

        RightGroup.Visibility = split ? Visibility.Visible : Visibility.Collapsed;
        Splitter.Visibility = split ? Visibility.Visible : Visibility.Collapsed;

        RightCol.Width = split ? new GridLength(1, GridUnitType.Star) : new GridLength(0);
        SplitterCol.Width = split ? new GridLength(5) : new GridLength(0);
    }
}
