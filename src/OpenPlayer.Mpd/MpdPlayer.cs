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

    private Task SendAsync(string command, CancellationToken ct) => client.ExecuteAsync([command], ct);
}
