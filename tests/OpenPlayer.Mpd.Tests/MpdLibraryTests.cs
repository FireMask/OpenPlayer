using System.Text;

namespace OpenPlayer.Mpd.Tests;

public class MpdLibraryTests
{
    private static MpdLibrary LibraryFor(FakeMpdServer server) => new(new MpdClient(server.Options()));

    // 3 carpetas mezcladas entre 150 pistas, más una playlist que debe ignorarse.
    private static string RootListing()
    {
        var sb = new StringBuilder();
        for (var i = 0; i < 150; i++)
        {
            if (i is 0 or 70 or 149)
                sb.Append($"directory: Dir{i}\nLast-Modified: 2026-01-01T00:00:00Z\n");
            sb.Append($"file: t{i:000}.mp3\nTitle: T{i}\nduration: 61.5\n");
        }
        sb.Append("playlist: Viaje.m3u\nLast-Modified: 2026-01-01T00:00:00Z\nOK\n");
        return sb.ToString();
    }

    [Fact]
    public async Task Browse_root_pages_with_directories_first_and_skips_playlists()
    {
        await using var server = new FakeMpdServer { Respond = _ => RootListing() };
        var library = LibraryFor(server);

        var first = await library.BrowseAsync("", 0);
        var second = await library.BrowseAsync("", 100);
        await server.AllClosed();

        Assert.Equal([["lsinfo"], ["lsinfo"]], server.Connections);
        Assert.Equal(153, first.Total);
        Assert.Equal(100, first.Entries.Count);
        Assert.Equal(["Dir0", "Dir70", "Dir149"], first.Entries.Take(3).Select(e => e.Uri));
        Assert.All(first.Entries.Take(3), e => Assert.Null(e.Track));
        Assert.Equal("t000.mp3", first.Entries[3].Uri);
        Assert.Equal(100, second.Offset);
        Assert.Equal(53, second.Entries.Count);
        Assert.Equal("t149.mp3", second.Entries[^1].Uri);
        Assert.DoesNotContain(first.Entries.Concat(second.Entries), e => e.Uri.Contains("Viaje"));
    }

    [Fact]
    public async Task Browse_quotes_path_and_parses_tracks_with_missing_metadata()
    {
        await using var server = new FakeMpdServer
        {
            Respond = _ => "file: Rock/a.mp3\nTitle: A\nArtist: X\nAlbum: Y\nduration: 210.7\nfile: Rock/b.mp3\nOK\n",
        };

        var page = await LibraryFor(server).BrowseAsync("Rock \"live\"", 0);
        await server.AllClosed();

        Assert.Equal([["lsinfo \"Rock \\\"live\\\"\""]], server.Connections);
        var a = page.Entries[0].Track!;
        Assert.Equal(("A", "X", "Y"), (a.Title, a.Artist, a.Album));
        Assert.Equal(TimeSpan.FromSeconds(210.7), a.Duration);
        var b = page.Entries[1].Track!;
        Assert.Equal("Rock/b.mp3", b.Uri);
        Assert.Null(b.Title);
        Assert.Null(b.Duration);
    }

    [Fact]
    public async Task Search_sends_search_any_and_pages()
    {
        await using var server = new FakeMpdServer { Respond = _ => "file: a.mp3\nTitle: Thunder\nOK\n" };

        var page = await LibraryFor(server).SearchAsync("thunder", 0);
        await server.AllClosed();

        Assert.Equal([["search any \"thunder\""]], server.Connections);
        Assert.Equal(1, page.Total);
        Assert.Equal("Thunder", page.Entries[0].Track!.Title);
    }

    [Fact]
    public async Task PlayTrack_sends_clear_add_play_in_one_connection()
    {
        await using var server = new FakeMpdServer();

        await LibraryFor(server).PlayTrackAsync("Rock/AC DC/01.flac");
        await server.AllClosed();

        Assert.Equal([["clear", "add \"Rock/AC DC/01.flac\"", "play 0"]], server.Connections);
    }

    [Fact]
    public async Task Ack_throws_MpdException()
    {
        await using var server = new FakeMpdServer { Respond = _ => "ACK [50@0] {lsinfo} No such directory\n" };

        var e = await Assert.ThrowsAsync<MpdException>(() => LibraryFor(server).BrowseAsync("nope", 0));

        Assert.Contains("No such directory", e.Message);
    }
}
