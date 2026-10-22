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
        Assert.Equal(offset + 1, page.Entries[0].Id);
    }

    [Theory]
    [InlineData("Id: x\n")]
    [InlineData("Id: -1\n")]
    [InlineData("")]
    public async Task Get_invalid_or_missing_id_is_null(string idLine)
    {
        await using var server = new FakeMpdServer { Respond = _ => $"file: x.mp3\nPos: 0\n{idLine}OK\n" };

        var page = await QueueFor(server).GetAsync(0);

        Assert.Null(page.Entries[0].Id);
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

    // Clave = comando MPD esperado.
    private static readonly Dictionary<string, Func<MpdQueue, Task>> Edits = new()
    {
        ["deleteid 17"] = q => q.RemoveAsync(17),
        ["moveid 17 2"] = q => q.MoveAsync(17, 2),
        ["clear"] = q => q.ClearAsync(),
    };

    [Theory]
    [InlineData("deleteid 17")]
    [InlineData("moveid 17 2")]
    [InlineData("clear")]
    public async Task Edits_send_exact_command(string expected)
    {
        await using var server = new FakeMpdServer();

        await Edits[expected](QueueFor(server));
        await server.AllClosed();

        Assert.Equal([[expected]], server.Connections);
    }

    [Fact]
    public async Task Add_appends_quoted_uri()
    {
        await using var server = new FakeMpdServer();

        await QueueFor(server).AddAsync("Rock/\"live\".flac", next: false);
        await server.AllClosed();

        Assert.Equal([["add \"Rock/\\\"live\\\".flac\""]], server.Connections);
    }

    [Fact]
    public async Task Add_next_inserts_after_current_song()
    {
        await using var server = new FakeMpdServer
        {
            Respond = c => c == "status" ? "state: play\nsong: 2\nsongid: 3\nOK\n" : "OK\n",
        };

        await QueueFor(server).AddAsync("a.flac", next: true);
        await server.AllClosed();

        Assert.Equal([["status"], ["add \"a.flac\" 3"]], server.Connections);
    }

    [Fact]
    public async Task Add_next_without_current_song_appends()
    {
        await using var server = new FakeMpdServer { Respond = c => c == "status" ? "state: stop\nOK\n" : "OK\n" };

        await QueueFor(server).AddAsync("Rock", next: true);
        await server.AllClosed();

        Assert.Equal([["status"], ["add \"Rock\""]], server.Connections);
    }

    [Fact]
    public async Task Save_sends_quoted_name()
    {
        await using var server = new FakeMpdServer();

        await QueueFor(server).SaveAsync("Ñandú \"x\"");
        await server.AllClosed();

        Assert.Equal([["save \"Ñandú \\\"x\\\"\""]], server.Connections);
    }

    [Fact]
    public async Task Save_existing_name_throws_MpdException()
    {
        await using var server = new FakeMpdServer { Respond = _ => "ACK [56@0] {save} Playlist already exists\n" };

        var e = await Assert.ThrowsAsync<MpdException>(() => QueueFor(server).SaveAsync("Viaje"));

        Assert.Contains("Playlist already exists", e.Message);
    }

    [Fact]
    public async Task Negative_edits_throw_without_connecting()
    {
        await using var server = new FakeMpdServer();
        var queue = QueueFor(server);

        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => queue.RemoveAsync(-1));
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => queue.MoveAsync(-1, 0));
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => queue.MoveAsync(17, -1));
        Assert.Empty(server.Connections);
    }

    [Fact]
    public async Task Remove_unknown_id_throws_MpdException()
    {
        await using var server = new FakeMpdServer { Respond = _ => "ACK [50@0] {deleteid} No such song\n" };

        var e = await Assert.ThrowsAsync<MpdException>(() => QueueFor(server).RemoveAsync(99));

        Assert.Contains("No such song", e.Message);
    }

    [Fact]
    public async Task Ack_throws_MpdException()
    {
        await using var server = new FakeMpdServer { Respond = _ => "ACK [2@0] {play} Bad song index\n" };

        var e = await Assert.ThrowsAsync<MpdException>(() => QueueFor(server).PlayAsync(99));

        Assert.Contains("Bad song index", e.Message);
    }
}
