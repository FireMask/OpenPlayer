using System.Text;
using OpenPlayer.Core.Interfaces;

namespace OpenPlayer.Mpd.Tests;

public class MpdPlaylistStoreTests
{
    private const string Listing = "playlist: Viaje\nLast-Modified: 2026-01-01T00:00:00Z\nplaylist: Gym\nLast-Modified: 2026-01-01T00:00:00Z\nOK\n";

    private static MpdPlaylistStore StoreFor(FakeMpdServer server) => new(new MpdClient(server.Options()));

    // Clave = comandos MPD esperados en una conexión.
    private static readonly Dictionary<string, Func<IPlaylistStore, Task>> Calls = new()
    {
        ["rename \"Viaje\" \"Viaje 2026\""] = s => s.RenameAsync("Viaje", "Viaje 2026"),
        ["rm \"Ñandú \\\"x\\\"\""] = s => s.DeleteAsync("Ñandú \"x\""),
        ["playlistadd \"Viaje\" \"Rock/AC DC\""] = s => s.AddAsync("Viaje", "Rock/AC DC"),
        ["playlistdelete \"Viaje\" 3"] = s => s.RemoveAsync("Viaje", 3),
        ["playlistmove \"Viaje\" 3 2"] = s => s.MoveAsync("Viaje", 3, 2),
        ["clear|load \"Viaje\"|play 4"] = s => s.PlayAsync("Viaje", 4),
    };

    [Theory]
    [InlineData("rename \"Viaje\" \"Viaje 2026\"")]
    [InlineData("rm \"Ñandú \\\"x\\\"\"")]
    [InlineData("playlistadd \"Viaje\" \"Rock/AC DC\"")]
    [InlineData("playlistdelete \"Viaje\" 3")]
    [InlineData("playlistmove \"Viaje\" 3 2")]
    [InlineData("clear|load \"Viaje\"|play 4")]
    public async Task Sends_exact_commands(string expected)
    {
        await using var server = new FakeMpdServer();

        await Calls[expected](StoreFor(server));
        await server.AllClosed();

        Assert.Equal([[.. expected.Split('|')]], server.Connections);
    }

    [Fact]
    public async Task List_returns_names_in_order()
    {
        await using var server = new FakeMpdServer { Respond = _ => Listing };

        Assert.Equal(["Viaje", "Gym"], await StoreFor(server).ListAsync());
        Assert.Equal([["listplaylists"]], server.Connections);
    }

    [Fact]
    public async Task Get_pages_listplaylistinfo()
    {
        var sb = new StringBuilder();
        for (var i = 0; i < 120; i++)
            sb.Append($"file: t{i}.mp3\nTitle: T{i}\n");
        await using var server = new FakeMpdServer { Respond = _ => sb + "OK\n" };

        var page = await StoreFor(server).GetAsync("Viaje", 100);
        await server.AllClosed();

        Assert.Equal([["listplaylistinfo \"Viaje\""]], server.Connections);
        Assert.Equal((100, 120, 20), (page.Offset, page.Total, page.Entries.Count));
        Assert.Equal("t100.mp3", page.Entries[0].Uri);
    }

    [Fact]
    public async Task Create_new_sends_playlistclear()
    {
        await using var server = new FakeMpdServer { Respond = c => c == "listplaylists" ? Listing : "OK\n" };

        await StoreFor(server).CreateAsync("Nueva");
        await server.AllClosed();

        Assert.Equal([["listplaylists"], ["playlistclear \"Nueva\""]], server.Connections);
    }

    [Fact]
    public async Task Create_existing_throws_without_playlistclear()
    {
        await using var server = new FakeMpdServer { Respond = _ => Listing };

        var e = await Assert.ThrowsAsync<MpdException>(() => StoreFor(server).CreateAsync("Viaje"));
        await server.AllClosed();

        Assert.Equal("Playlist 'Viaje' already exists", e.Message);
        Assert.Equal([["listplaylists"]], server.Connections);
    }

    [Fact]
    public async Task Ack_for_missing_playlist_throws_MpdException()
    {
        await using var server = new FakeMpdServer { Respond = _ => "ACK [50@0] {rm} No such playlist\n" };

        var e = await Assert.ThrowsAsync<MpdException>(() => StoreFor(server).DeleteAsync("Nope"));

        Assert.Contains("No such playlist", e.Message);
    }

    [Fact]
    public async Task Invalid_name_throws_without_connecting()
    {
        await using var server = new FakeMpdServer();

        await Assert.ThrowsAsync<ArgumentException>(() => StoreFor(server).DeleteAsync("a/b"));

        Assert.Empty(server.Connections);
    }
}
