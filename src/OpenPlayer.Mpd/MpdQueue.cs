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
        return client.ExecuteAsync(["consume 1", $"play {position.ToString(CultureInfo.InvariantCulture)}"], ct);
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

    // next: status y add en dos conexiones (ExecuteAsync envía el lote entero antes de leer); el lock del Service
    // evita que otro cliente se intercale. Sin pista actual no hay "siguiente": agrega al final.
    public async Task AddAsync(string uri, bool next, CancellationToken ct = default)
    {
        var command = $"add {MpdClient.Quote(uri)}";
        if (next)
        {
            var song = (await client.ExecuteAsync(["status"], ct))[0].Get("song");
            if (int.TryParse(song, NumberStyles.None, CultureInfo.InvariantCulture, out var current))
                command += " " + (current + 1).ToString(CultureInfo.InvariantCulture);
        }
        await client.ExecuteAsync([command], ct);
    }

    public Task SaveAsync(string name, CancellationToken ct = default) =>
        client.ExecuteAsync([$"save {MpdClient.Quote(name)}"], ct);

    // SPEC 14: cada canción terminada o saltada sale de la cola.
    public Task EnableConsumeAsync(CancellationToken ct = default) => client.ExecuteAsync(["consume 1"], ct);

    // plchangesposid 0: pares cpos/Id de toda la cola, más livianos que playlistinfo.
    public async Task<IReadOnlyList<int>> IdsAsync(CancellationToken ct = default)
    {
        var response = (await client.ExecuteAsync(["plchangesposid 0"], ct))[0];
        return [.. response.Pairs.Where(p => p.Key == "Id")
            .Select(p => int.Parse(p.Value, NumberStyles.None, CultureInfo.InvariantCulture))];
    }
}
