using OpenPlayer.Core.Commands;
using OpenPlayer.Core.Messages;

namespace OpenPlayer.Core.Tests;

public class IpcMessageParserTests
{
    [Fact]
    public void Parses_button_pressed_with_sequence()
    {
        Assert.True(IpcMessageParser.TryParse("""{"type":"button.pressed","button":"next","sequence":1}""", out var message, out var error));
        Assert.Equal(new ButtonPressed(ButtonName.Next, 1), message);
        Assert.Null(error);
    }

    [Fact]
    public void Parses_button_pressed_without_sequence()
    {
        Assert.True(IpcMessageParser.TryParse("""{"type":"button.pressed","button":"play_pause"}""", out var message, out _));
        Assert.Equal(new ButtonPressed(ButtonName.PlayPause, null), message);
    }

    [Fact]
    public void Parses_snapshot_request()
    {
        Assert.True(IpcMessageParser.TryParse("""{"type":"player.get_snapshot"}""", out var message, out _));
        Assert.IsType<SnapshotRequested>(message);
    }

    [Fact]
    public void Ignores_extra_fields_with_utf8()
    {
        Assert.True(IpcMessageParser.TryParse("""{"type":"button.pressed","button":"menu","origen":"botón café","ts":5}""", out var message, out _));
        Assert.Equal(new ButtonPressed(ButtonName.Menu, null), message);
    }

    [Theory]
    [InlineData("hola", "invalid JSON")]
    [InlineData("""{"type":"player.get_snapshot" """, "invalid JSON")]
    [InlineData("[1,2]", "invalid JSON")]
    [InlineData("\"button.pressed\"", "invalid JSON")]
    [InlineData("""{"button":"next"}""", "missing type")]
    [InlineData("""{"type":3}""", "missing type")]
    [InlineData("""{"type":"player.reboot"}""", "unknown type 'player.reboot'")]
    [InlineData("""{"type":"button.pressed"}""", "invalid button ''")]
    [InlineData("""{"type":"button.pressed","button":"foo"}""", "invalid button 'foo'")]
    [InlineData("""{"type":"button.pressed","button":"Next"}""", "invalid button 'Next'")]
    [InlineData("""{"type":"button.pressed","button":3}""", "invalid button '3'")]
    [InlineData("""{"type":"button.pressed","button":"next","sequence":"1"}""", "invalid sequence")]
    [InlineData("""{"type":"button.pressed","button":"next","sequence":1.5}""", "invalid sequence")]
    public void Rejects_invalid_messages(string line, string expected)
    {
        Assert.False(IpcMessageParser.TryParse(line, out var message, out var error));
        Assert.Null(message);
        Assert.Equal(expected, error);
    }
}
