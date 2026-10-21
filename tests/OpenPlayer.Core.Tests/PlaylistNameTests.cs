using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Tests;

public class PlaylistNameTests
{
    [Theory]
    [InlineData("Viaje 2026")]
    [InlineData("Ñandú")]
    [InlineData("a.b")]
    public void EnsureValid_accepts(string name) =>
        Assert.Equal(name, PlaylistName.EnsureValid(name));

    [Fact]
    public void EnsureValid_accepts_100_characters() =>
        PlaylistName.EnsureValid(new string('a', 100));

    [Theory]
    [InlineData("")]
    [InlineData("a/b")]
    [InlineData("a\\b")]
    [InlineData("a\nb")]
    [InlineData("a\rb")]
    [InlineData(".x")]
    public void EnsureValid_rejects(string name) =>
        Assert.Throws<ArgumentException>(() => PlaylistName.EnsureValid(name));

    [Fact]
    public void EnsureValid_rejects_101_characters() =>
        Assert.Throws<ArgumentException>(() => PlaylistName.EnsureValid(new string('a', 101)));
}
