using System.Globalization;
using OpenPlayer.Core.Interfaces;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Mpd;

/// <summary><see cref="IPlaylistStore"/> sobre las playlists guardadas de MPD (<c>.m3u</c> en <c>playlist_directory</c>).</summary>
public sealed class MpdPlaylistStore(MpdClient client) : IPlaylistStore
{
    public async Task<IReadOnlyList<string>> ListAsync(CancellationToken ct = default)
    {
        var response = (await client.ExecuteAsync(["listplaylists"], ct))[0];
        return [.. response.Pairs.Where(p => p.Key == "playlist").Select(p => p.Value)];
    }

    public async Task<LibraryPage> GetAsync(string name, int offset, CancellationToken ct = default)
    {
        var response = (await client.ExecuteAsync([$"listplaylistinfo {Name(name)}"], ct))[0];
        return MpdEntryParser.Page(MpdEntryParser.Parse(response), offset);
    }

    // MPD no tiene "crear vacía" y en 0.23 playlistclear de un nombre inexistente responde "No such playlist":
    // playlistadd de la raíz ("") crea el .m3u con toda la biblioteca y playlistclear lo vacía.
    // ponytail: escribe la biblioteca entera una vez; si pesa con decenas de miles de pistas, agregar una sola pista.
    public async Task CreateAsync(string name, CancellationToken ct = default)
    {
        var quoted = Name(name);
        if ((await ListAsync(ct)).Contains(name))
            throw new MpdException($"playlistclear {quoted}", $"Playlist '{name}' already exists");
        await client.ExecuteAsync([$"playlistadd {quoted} {MpdClient.Quote("")}", $"playlistclear {quoted}"], ct);
    }

    public Task RenameAsync(string name, string newName, CancellationToken ct = default) =>
        Send($"rename {Name(name)} {Name(newName)}", ct);

    public Task DeleteAsync(string name, CancellationToken ct = default) => Send($"rm {Name(name)}", ct);

    public Task AddAsync(string name, string uri, CancellationToken ct = default) =>
        Send($"playlistadd {Name(name)} {MpdClient.Quote(uri)}", ct);

    public Task RemoveAsync(string name, int position, CancellationToken ct = default) =>
        Send($"playlistdelete {Name(name)} {Number(position)}", ct);

    public Task MoveAsync(string name, int from, int to, CancellationToken ct = default) =>
        Send($"playlistmove {Name(name)} {Number(from)} {Number(to)}", ct);

    public Task PlayAsync(string name, int position, CancellationToken ct = default) =>
        client.ExecuteAsync(["clear", "consume 1", $"load {Name(name)}", $"play {Number(position)}"], ct);  // consume: SPEC 14

    private Task Send(string command, CancellationToken ct) => client.ExecuteAsync([command], ct);

    private static string Name(string name) => MpdClient.Quote(PlaylistName.EnsureValid(name));

    private static string Number(int value)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(value);
        return value.ToString(CultureInfo.InvariantCulture);
    }
}
