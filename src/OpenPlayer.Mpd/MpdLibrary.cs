using OpenPlayer.Core.Interfaces;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Mpd;

/// <summary><see cref="ILibrary"/> sobre la base de MPD; pagina sobre la respuesta completa (MPD 0.23 no pagina <c>lsinfo</c>).</summary>
public sealed class MpdLibrary(MpdClient client) : ILibrary
{
    public async Task<LibraryPage> BrowseAsync(string path, int offset, CancellationToken ct = default)
    {
        var command = path.Length == 0 ? "lsinfo" : $"lsinfo {MpdClient.Quote(path)}";
        var entries = MpdEntryParser.Parse((await client.ExecuteAsync([command], ct))[0]);
        // OrderBy es estable: carpetas primero, cada grupo en el orden de MPD.
        return MpdEntryParser.Page(entries.OrderBy(e => e.Track is not null), offset);
    }

    public async Task<LibraryPage> SearchAsync(string query, int offset, CancellationToken ct = default)
    {
        var response = (await client.ExecuteAsync([$"search any {MpdClient.Quote(query)}"], ct))[0];
        return MpdEntryParser.Page(MpdEntryParser.Parse(response), offset);
    }

    public Task PlayTrackAsync(string uri, CancellationToken ct = default) =>
        client.ExecuteAsync(["clear", "consume 1", $"add {MpdClient.Quote(uri)}", "play 0"], ct);  // consume: SPEC 14
}
