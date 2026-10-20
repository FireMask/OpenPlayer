using OpenPlayer.Core.Commands;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Tests;

public class ButtonCommandHandlerTests
{
    private readonly FakePlayer _player = new();
    private readonly PlayerSettings _settings = new();

    private Task Press(ButtonName button) => new ButtonCommandHandler(_player, _settings).HandleAsync(button);

    [Fact]
    public async Task PlayPause_toggles_once()
    {
        await Press(ButtonName.PlayPause);
        Assert.Equal(["TogglePlayback"], _player.Calls);
    }

    [Fact]
    public async Task Next_goes_next_once()
    {
        await Press(ButtonName.Next);
        Assert.Equal(["Next"], _player.Calls);
    }

    [Fact]
    public async Task Menu_does_nothing()
    {
        await Press(ButtonName.Menu);
        Assert.Empty(_player.Calls);
    }

    [Fact]
    public async Task Undefined_button_throws() =>
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => Press((ButtonName)99));
}
