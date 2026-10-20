using OpenPlayer.Core.Interfaces;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Mpd.Tests;

public class MpdPlayerTests
{
    private static MpdPlayer PlayerFor(FakeMpdServer server) =>
        new(new MpdClient(server.Options()), TimeProvider.System);

    public static TheoryData<string, Func<IPlayer, Task>> SingleCommands => new()
    {
        { "play", p => p.PlayAsync() },
        { "pause 1", p => p.PauseAsync() },
        { "next", p => p.NextAsync() },
        { "previous", p => p.PreviousAsync() },
        { "seekcur 0", p => p.SeekAsync(TimeSpan.Zero) },
        { "seekcur 1.5", p => p.SeekAsync(TimeSpan.FromSeconds(1.5)) },
        { "setvol 0", p => p.SetVolumeAsync(0) },
        { "setvol 100", p => p.SetVolumeAsync(100) },
    };

    [Theory]
    [MemberData(nameof(SingleCommands))]
    public async Task Sends_exact_command(string expected, Func<IPlayer, Task> call)
    {
        await using var server = new FakeMpdServer();

        await call(PlayerFor(server));

        Assert.Equal([[expected]], server.Connections);
    }

    [Theory]
    [InlineData("play", "pause 1")]
    [InlineData("pause", "pause 0")]
    [InlineData("stop", "play")]
    public async Task Toggle_decides_from_status(string state, string expected)
    {
        await using var server = new FakeMpdServer
        {
            Respond = c => c == "status" ? $"state: {state}\nOK\n" : "OK\n",
        };

        await PlayerFor(server).TogglePlaybackAsync();

        Assert.Equal([["status"], [expected]], server.Connections);
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(101)]
    public async Task SetVolume_out_of_range_throws_without_connecting(int volume)
    {
        await using var server = new FakeMpdServer();

        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => PlayerFor(server).SetVolumeAsync(volume));

        Assert.Empty(server.Connections);
    }

    [Fact]
    public async Task Seek_negative_throws_without_connecting()
    {
        await using var server = new FakeMpdServer();

        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(
            () => PlayerFor(server).SeekAsync(TimeSpan.FromSeconds(-1)));

        Assert.Empty(server.Connections);
    }

    [Fact]
    public async Task Snapshot_uses_one_connection()
    {
        await using var server = new FakeMpdServer
        {
            Respond = c => c == "status"
                ? "volume: 35\nstate: pause\nelapsed: 10.000\nOK\n"
                : "file: a.flac\nTitle: Song\nArtist: Band\nOK\n",
        };

        var snapshot = await PlayerFor(server).GetSnapshotAsync();

        Assert.Equal([["status", "currentsong"]], server.Connections);
        Assert.Equal(PlaybackState.Paused, snapshot.State);
        Assert.Equal("Band", snapshot.CurrentTrack?.Artist);
        Assert.Equal(35, snapshot.Volume);
    }
}
