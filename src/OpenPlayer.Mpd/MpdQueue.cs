using System.Globalization;
using OpenPlayer.Core.Interfaces;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Mpd;

/// <summary><see cref="IQueue"/> sobre la cola de MPD; pagina sobre la respuesta completa de <c>playlistinfo</c>.</summary>
public sealed class MpdQueue(MpdClient client) : IQueue
{
    public async Task<LibraryPage> GetAsync(int offset, CancellationToken ct = default)
    {
        var response = (await client.ExecuteAsync(["playlistinfo"], ct))[0];
        return MpdEntryParser.Page(MpdEntryParser.Parse(response), offset);
    }

    public Task PlayAsync(int position, CancellationToken ct = default)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(position);
        return client.ExecuteAsync([$"play {position.ToString(CultureInfo.InvariantCulture)}"], ct);
    }

    public Task RemoveAsync(int id, CancellationToken ct = default)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(id);
        return client.ExecuteAsync([$"deleteid {id.ToString(CultureInfo.InvariantCulture)}"], ct);
    }

    public Task MoveAsync(int id, int to, CancellationToken ct = default)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(id);
        ArgumentOutOfRangeException.ThrowIfNegative(to);
        return client.ExecuteAsync(
            [$"moveid {id.ToString(CultureInfo.InvariantCulture)} {to.ToString(CultureInfo.InvariantCulture)}"], ct);
    }

    public Task ClearAsync(CancellationToken ct = default) => client.ExecuteAsync(["clear"], ct);
}
