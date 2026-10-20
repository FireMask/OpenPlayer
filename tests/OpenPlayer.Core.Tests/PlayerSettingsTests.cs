using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Tests;

public class PlayerSettingsTests
{
    [Fact]
    public void Defaults_match_example_config()
    {
        var settings = new PlayerSettings();

        Assert.Equal(5, settings.VolumeStep);
        Assert.Equal(35, settings.InitialVolume);
        Assert.Equal(TimeSpan.FromSeconds(3), settings.PreviousRestartThreshold);
    }

    [Fact]
    public void Accepts_bounds()
    {
        _ = new PlayerSettings(volumeStep: 1, initialVolume: 0, previousRestartThreshold: TimeSpan.Zero);
        _ = new PlayerSettings(volumeStep: 100, initialVolume: 100);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(101)]
    public void Rejects_invalid_volume_step(int step) =>
        Assert.Throws<ArgumentOutOfRangeException>(() => new PlayerSettings(volumeStep: step));

    [Theory]
    [InlineData(-1)]
    [InlineData(101)]
    public void Rejects_invalid_initial_volume(int volume) =>
        Assert.Throws<ArgumentOutOfRangeException>(() => new PlayerSettings(initialVolume: volume));

    [Fact]
    public void Rejects_negative_threshold() =>
        Assert.Throws<ArgumentOutOfRangeException>(
            () => new PlayerSettings(previousRestartThreshold: TimeSpan.FromMilliseconds(-1)));
}
