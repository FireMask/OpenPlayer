using System.Text;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Mpd.Tests;

public class MpdQueueTests
{
    private static MpdQueue QueueFor(FakeMpdServer server) => new(new MpdClient(server.Options()));

    private static string Queue(int count)
    {
        var sb = new StringBuilder();
        for (var i = 0; i < count; i++)
            sb.Append($"file: t{i}.mp3\nTitle: T{i}\nPos: {i}\nId: {i + 1}\n");
        return sb + "OK\n";
    }

    [Theory]
    [InlineData(0, 100, "t0.mp3")]
    [InlineData(100, 20, "t100.mp3")]
    public async Task Get_pages_playlistinfo(int offset, int count, string first)
    {
        await using var server = new FakeMpdServer { Respond = _ => Queue(120) };

        var page = await QueueFor(server).GetAsync(offset);
        await server.AllClosed();

        Assert.Equal([["playlistinfo"]], server.Connections);
        Assert.Equal((offset, 120, count), (page.Offset, page.Total, page.Entries.Count));
        Assert.Equal(first, page.Entries[0].Uri);
    }

    [Fact]
    public async Task Get_keeps_missing_metadata_null()
    {
        await using var server = new FakeMpdServer
        {
            Respond = _ => "file: x.mp3\nPos: 0\nId: 1\nfile: a.flac\nTitle: A\nArtist: B\nAlbum: C\nduration: 225.4\nPos: 1\nId: 2\nOK\n",
        };

        var page = await QueueFor(server).GetAsync(0);

        Assert.Equal(new Track("x.mp3", null, null, null, null), page.Entries[0].Track);
        Assert.Equal(new Track("a.flac", "A", "B", "C", TimeSpan.FromSeconds(225.4)), page.Entries[1].Track);
    }

    [Fact]
    public async Task Get_empty_queue()
    {
        await using var server = new FakeMpdServer { Respond = _ => "OK\n" };

        var page = await QueueFor(server).GetAsync(0);

        Assert.Equal((0, 0, 0), (page.Offset, page.Total, page.Entries.Count));
    }

    [Fact]
    public async Task Play_sends_play_n()
    {
        await using var server = new FakeMpdServer();

        await QueueFor(server).PlayAsync(3);
        await server.AllClosed();

        Assert.Equal([["play 3"]], server.Connections);
    }

    [Fact]
    public async Task Ack_throws_MpdException()
    {
        await using var server = new FakeMpdServer { Respond = _ => "ACK [2@0] {play} Bad song index\n" };

        var e = await Assert.ThrowsAsync<MpdException>(() => QueueFor(server).PlayAsync(99));

        Assert.Contains("Bad song index", e.Message);
    }
}
