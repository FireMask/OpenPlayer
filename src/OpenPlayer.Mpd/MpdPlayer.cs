using System.Globalization;
using OpenPlayer.Core.Interfaces;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Mpd;

public sealed class MpdPlayer(MpdClient client, TimeProvider time) : IPlayer
{
    public Task PlayAsync(CancellationToken ct = default) => SendAsync("play", ct);

    public Task PauseAsync(CancellationToken ct = default) => SendAsync("pause 1", ct);

    // "pause" sin argumento está deprecado y no arranca desde stop.
    public async Task TogglePlaybackAsync(CancellationToken ct = default)
    {
        var status = (await client.ExecuteAsync(["status"], ct))[0];
        var command = status.Get("state") switch
        {
            "play" => "pause 1",
            "pause" => "pause 0",
            _ => "play",
        };
        await SendAsync(command, ct);
    }

    public Task NextAsync(CancellationToken ct = default) => SendAsync("next", ct);

    // Con consume (SPEC 14) la actual está primera: MPD 0.24 reinicia la canción sin quitarla (medido en la Pi).
    public Task PreviousAsync(CancellationToken ct = default) => SendAsync("previous", ct);

    public Task SeekAsync(TimeSpan position, CancellationToken ct = default)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(position, TimeSpan.Zero);
        return SendAsync($"seekcur {position.TotalSeconds.ToString(CultureInfo.InvariantCulture)}", ct);
    }

    public Task SetVolumeAsync(int volume, CancellationToken ct = default) =>
        SendAsync($"setvol {Volume.EnsureValid(volume).ToString(CultureInfo.InvariantCulture)}", ct);

    // MPD responde con un job id y escanea en segundo plano.
    public Task UpdateLibraryAsync(CancellationToken ct = default) => SendAsync("update", ct);

    public async Task<PlaybackSnapshot> GetSnapshotAsync(CancellationToken ct = default)
    {
        var responses = await client.ExecuteAsync(["status", "currentsong"], ct);
        return MpdSnapshotParser.Parse(responses[0], responses[1], time.GetUtcNow());
    }

    public Task WaitForChangeAsync(CancellationToken ct = default) => client.IdleAsync(ct);

    // binarylimit (MPD ≥ 0.22.4): una carátula de hasta 1 MB llega en un solo trozo en vez de ~128 de 8 KB.
    private const string BinaryLimit = "binarylimit 1048576";
    private bool _binaryLimitSupported = true;

    // Incrustada (readpicture) y, si no hay, la de la carpeta (albumart). Una conexión por trozo.
    public async Task<Cover> GetCoverAsync(CancellationToken ct = default)
    {
        var song = (await client.ExecuteAsync(["currentsong"], ct))[0];
        var uri = song.Get("file");
        var id = int.TryParse(song.Get("Id"), NumberStyles.None, CultureInfo.InvariantCulture, out var i) ? i : (int?)null;
        if (uri is null)
            return new Cover(null, null, null);

        var picture = await ReadImageAsync("readpicture", uri, ct) ?? await ReadImageAsync("albumart", uri, ct);
        return new Cover(id, picture?.Mime, picture?.Data);
    }

    private async Task<(string? Mime, byte[] Data)?> ReadImageAsync(string command, string uri, CancellationToken ct)
    {
        byte[]? data = null;
        string? mime = null;
        var offset = 0;
        do
        {
            MpdResponse chunk;
            try
            {
                chunk = await ChunkAsync($"{command} {MpdClient.Quote(uri)} {offset.ToString(CultureInfo.InvariantCulture)}", ct);
            }
            catch (MpdException e) when (e.Message.StartsWith("[50@", StringComparison.Ordinal))
            {
                return null; // albumart sin archivo de carátula en la carpeta
            }
            if (chunk.Binary is null)
                return null; // readpicture sin imagen incrustada
            if (data is null)
            {
                var size = long.TryParse(chunk.Get("size"), NumberStyles.None, CultureInfo.InvariantCulture, out var s) ? s : -1;
                if (size > Cover.MaxBytes)
                    throw new CoverTooLargeException(size);
                if (size == 0)
                    return null;
                if (size < chunk.Binary.Length)
                    throw new MpdException(command, $"invalid size '{chunk.Get("size")}'");
                data = new byte[size];
                mime = chunk.Get("type");
            }
            if (chunk.Binary.Length == 0 || offset + chunk.Binary.Length > data.Length)
                throw new MpdException(command, "unexpected chunk length");
            chunk.Binary.CopyTo(data, offset);
            offset += chunk.Binary.Length;
        } while (offset < data.Length);
        return (mime, data);
    }

    private async Task<MpdResponse> ChunkAsync(string command, CancellationToken ct)
    {
        if (_binaryLimitSupported)
        {
            try
            {
                return (await client.ExecuteAsync([BinaryLimit, command], ct))[1];
            }
            catch (MpdException e) when (e.Command == BinaryLimit)
            {
                _binaryLimitSupported = false; // MPD viejo: trozos de 8 KB
            }
        }
        return (await client.ExecuteAsync([command], ct))[0];
    }

    private Task SendAsync(string command, CancellationToken ct) => client.ExecuteAsync([command], ct);
}
