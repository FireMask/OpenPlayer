using OpenPlayer.Core.Commands;

namespace OpenPlayer.Core.Tests;

public class ButtonNamesTests
{
    [Theory]
    [InlineData("play_pause", ButtonName.PlayPause)]
    [InlineData("previous", ButtonName.Previous)]
    [InlineData("next", ButtonName.Next)]
    [InlineData("volume_up", ButtonName.VolumeUp)]
    [InlineData("volume_down", ButtonName.VolumeDown)]
    [InlineData("menu", ButtonName.Menu)]
    [InlineData("refresh_library", ButtonName.RefreshLibrary)]
    [InlineData("seek_forward", ButtonName.SeekForward)]
    [InlineData("seek_backward", ButtonName.SeekBackward)]
    [InlineData("power_off", ButtonName.PowerOff)]
    public void Parses_ipc_names(string value, ButtonName expected)
    {
        Assert.True(ButtonNames.TryParse(value, out var button));
        Assert.Equal(expected, button);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("NEXT")]
    [InlineData("Play_Pause")]
    [InlineData(" next")]
    [InlineData("PlayPause")]
    [InlineData("power")]
    public void Rejects_anything_else(string? value) =>
        Assert.False(ButtonNames.TryParse(value, out _));
}
