using OpenPlayer.Core.Interfaces;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Mpd.Tests;

public class MpdPlayerTests
{
    private static MpdPlayer PlayerFor(FakeMpdServer server) =>
        new(new MpdClient(server.Options()), TimeProvider.System);

    // Clave = comando MPD esperado.
    private static readonly Dictionary<string, Func<IPlayer, Task>> Calls = new()
    {
        ["play"] = p => p.PlayAsync(),
        ["pause 1"] = p => p.PauseAsync(),
        ["next"] = p => p.NextAsync(),
        ["previous"] = p => p.PreviousAsync(),
        ["seekcur 0"] = p => p.SeekAsync(TimeSpan.Zero),
        ["seekcur 1.5"] = p => p.SeekAsync(TimeSpan.FromSeconds(1.5)),
        ["setvol 0"] = p => p.SetVolumeAsync(0),
        ["setvol 100"] = p => p.SetVolumeAsync(100),
        ["update"] = p => p.UpdateLibraryAsync(),
    };

    [Theory]
    [InlineData("play")]
    [InlineData("pause 1")]
    [InlineData("next")]
    [InlineData("previous")]
    [InlineData("seekcur 0")]
    [InlineData("seekcur 1.5")]
    [InlineData("setvol 0")]
    [InlineData("setvol 100")]
    [InlineData("update")]
    public async Task Sends_exact_command(string expected)
    {
        await using var server = new FakeMpdServer();

        await Calls[expected](PlayerFor(server));

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
    public async Task WaitForChange_sends_idle_with_subsystems()
    {
        await using var server = new FakeMpdServer { Respond = _ => "changed: player\nOK\n" };

        await PlayerFor(server).WaitForChangeAsync();
        await server.AllClosed();

        Assert.Equal([["idle player mixer playlist options"]], server.Connections);
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

    // Carátula (SPEC 19)

    private static byte[] Bytes(string text) => System.Text.Encoding.UTF8.GetBytes(text);

    private static byte[] Image(int length) => [.. Enumerable.Range(0, length).Select(i => (byte)(i * 31 % 251))];

    /// <summary>MPD falso con carátula incrustada y/o de carpeta, entregada en trozos de <paramref name="chunk"/> bytes.</summary>
    private static FakeMpdServer CoverServer(byte[]? embedded, byte[]? folder = null, int chunk = 1_000_000,
        bool binaryLimit = true, bool song = true, long? reportedSize = null)
    {
        byte[] Slice(byte[] data, string command, string type)
        {
            var offset = int.Parse(command[(command.LastIndexOf(' ') + 1)..]);
            var part = data.Skip(offset).Take(chunk).ToArray();
            return [.. Bytes($"size: {reportedSize ?? data.Length}\n{type}binary: {part.Length}\n"), .. part, .. Bytes("\nOK\n")];
        }

        return new FakeMpdServer
        {
            RespondBytes = c => c switch
            {
                "currentsong" => Bytes(song ? "file: Bad Bunny/01.flac\nId: 17\nOK\n" : "OK\n"),
                _ when c.StartsWith("binarylimit") => Bytes(binaryLimit ? "OK\n" : "ACK [5@0] {} unknown command \"binarylimit\"\n"),
                _ when c.StartsWith("readpicture \"Bad Bunny/01.flac\" ") =>
                    embedded is null ? Bytes("OK\n") : Slice(embedded, c, "type: image/jpeg\n"),
                _ when c.StartsWith("albumart \"Bad Bunny/01.flac\" ") =>
                    folder is null ? Bytes("ACK [50@0] {albumart} No file exists\n") : Slice(folder, c, ""),
                _ => Bytes("ACK [5@0] {} unexpected\n"),
            },
        };
    }

    [Fact]
    public async Task Cover_joins_embedded_chunks_byte_for_byte()
    {
        var image = Image(25_000);
        await using var server = CoverServer(image, chunk: 8_192);

        var cover = await PlayerFor(server).GetCoverAsync();

        Assert.Equal(new Cover(17, "image/jpeg", null), cover with { Data = null });
        Assert.Equal(image, cover.Data);
        var reads = server.Connections.Skip(1).ToList();
        Assert.Equal(4, reads.Count); // 25 000 bytes en trozos de 8 192
        Assert.All(reads, r => Assert.Equal("binarylimit 1048576", r[0]));
        Assert.Equal("readpicture \"Bad Bunny/01.flac\" 24576", reads[^1][1]);
    }

    [Fact]
    public async Task Cover_falls_back_to_folder_file()
    {
        var image = Image(3_000);
        await using var server = CoverServer(embedded: null, folder: image);

        var cover = await PlayerFor(server).GetCoverAsync();

        Assert.Equal(image, cover.Data);
        Assert.Null(cover.Mime);
        Assert.Equal(17, cover.SongId);
    }

    [Fact]
    public async Task Cover_without_embedded_or_folder_has_null_data()
    {
        await using var server = CoverServer(embedded: null);

        Assert.Equal(new Cover(17, null, null), await PlayerFor(server).GetCoverAsync());
    }

    [Fact]
    public async Task Cover_without_current_song_is_empty()
    {
        await using var server = CoverServer(Image(10), song: false);

        Assert.Equal(new Cover(null, null, null), await PlayerFor(server).GetCoverAsync());
        Assert.Equal([["currentsong"]], server.Connections);
    }

    [Fact]
    public async Task Cover_over_2_mb_throws_after_first_chunk()
    {
        await using var server = CoverServer(Image(1_000), chunk: 100, reportedSize: Cover.MaxBytes + 1);

        var e = await Assert.ThrowsAsync<CoverTooLargeException>(() => PlayerFor(server).GetCoverAsync());

        Assert.Equal(Cover.MaxBytes + 1, e.Size);
        Assert.Equal(2, server.Connections.Count); // currentsong + un solo trozo
    }

    [Fact]
    public async Task Cover_without_binarylimit_support_uses_plain_chunks()
    {
        var image = Image(5_000);
        await using var server = CoverServer(image, chunk: 2_000, binaryLimit: false);
        var player = PlayerFor(server);

        Assert.Equal(image, (await player.GetCoverAsync()).Data);
        Assert.Equal(image, (await player.GetCoverAsync()).Data); // recuerda que no hay binarylimit

        var connections = server.Connections;
        Assert.Equal(["binarylimit 1048576"], connections[1]);
        Assert.All(connections.Skip(2).Where(c => c[0] != "currentsong"), c => Assert.StartsWith("readpicture", c[0]));
    }
}
