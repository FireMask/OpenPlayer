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
    public async Task Previous_after_threshold_restarts_track()
    {
        _player.Snapshot = FakePlayer.SnapshotWith(position: TimeSpan.FromSeconds(5));
        await Press(ButtonName.Previous);
        Assert.Equal(["GetSnapshot", "Seek(00:00:00)"], _player.Calls);
    }

    [Theory]
    [InlineData(2.0)]
    [InlineData(3.0)]
    [InlineData(null)]
    public async Task Previous_at_or_before_threshold_goes_previous(double? seconds)
    {
        _player.Snapshot = FakePlayer.SnapshotWith(
            position: seconds is null ? null : TimeSpan.FromSeconds(seconds.Value));
        await Press(ButtonName.Previous);
        Assert.Equal(["GetSnapshot", "Previous"], _player.Calls);
    }

    [Fact]
    public async Task Undefined_button_throws() =>
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => Press((ButtonName)99));
}
