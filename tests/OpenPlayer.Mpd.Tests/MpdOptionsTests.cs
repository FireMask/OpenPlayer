namespace OpenPlayer.Mpd.Tests;

public class MpdOptionsTests
{
    private static readonly TimeSpan OneSecond = TimeSpan.FromSeconds(1);

    [Fact]
    public void Accepts_valid_values()
    {
        var o = new MpdOptions("127.0.0.1", 6600, OneSecond);
        Assert.Equal(("127.0.0.1", 6600, OneSecond), (o.Host, o.Port, o.ConnectTimeout));
    }

    [Theory]
    [InlineData("")]
    [InlineData(" ")]
    public void Rejects_empty_host(string host) =>
        Assert.Throws<ArgumentException>(() => new MpdOptions(host, 6600, OneSecond));

    [Theory]
    [InlineData(0)]
    [InlineData(65536)]
    public void Rejects_invalid_port(int port) =>
        Assert.Throws<ArgumentOutOfRangeException>(() => new MpdOptions("h", port, OneSecond));

    [Fact]
    public void Rejects_non_positive_timeout() =>
        Assert.Throws<ArgumentOutOfRangeException>(() => new MpdOptions("h", 6600, TimeSpan.Zero));
}
