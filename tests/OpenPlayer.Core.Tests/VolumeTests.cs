using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Tests;

public class VolumeTests
{
    [Theory]
    [InlineData(0)]
    [InlineData(100)]
    public void EnsureValid_accepts_bounds(int volume) =>
        Assert.Equal(volume, Volume.EnsureValid(volume));

    [Theory]
    [InlineData(-1)]
    [InlineData(101)]
    public void EnsureValid_rejects_out_of_range(int volume) =>
        Assert.Throws<ArgumentOutOfRangeException>(() => Volume.EnsureValid(volume));
}
