using System.Globalization;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Mpd;

/// <summary>Parte una respuesta de <c>lsinfo</c>/<c>search</c>/<c>listplaylistinfo</c> en entradas.</summary>
internal static class MpdEntryParser
{
    /// <summary>Carpetas y pistas en el orden de MPD; las entradas <c>playlist:</c> se descartan.</summary>
    public static List<LibraryEntry> Parse(MpdResponse response)
    {
        var entries = new List<LibraryEntry>();
        string? file = null;
        Dictionary<string, string> tags = [];

        void Flush()
        {
            if (file is not null)
                entries.Add(new LibraryEntry(file, new Track(file, tags.GetValueOrDefault("Title"),
                    tags.GetValueOrDefault("Artist"), tags.GetValueOrDefault("Album"),
                    MpdSnapshotParser.Seconds(tags.GetValueOrDefault("duration"))),
                    // Id solo viene en playlistinfo (la cola); lsinfo y listplaylistinfo lo dejan null.
                    int.TryParse(tags.GetValueOrDefault("Id"), NumberStyles.None, CultureInfo.InvariantCulture, out var id)
                        ? id
                        : null));
            file = null;
            tags = [];
        }

        foreach (var (key, value) in response.Pairs)
        {
            switch (key)
            {
                case "file":
                    Flush();
                    file = value;
                    break;
                case "directory":
                    Flush();
                    entries.Add(new LibraryEntry(value, null));
                    break;
                case "playlist":
                    Flush();
                    break;
                default:
                    if (file is not null)
                        tags.TryAdd(key, value);
                    break;
            }
        }
        Flush();
        return entries;
    }

    public static LibraryPage Page(IEnumerable<LibraryEntry> entries, int offset)
    {
        var all = entries.ToList();
        return new LibraryPage(offset, all.Count, [.. all.Skip(offset).Take(LibraryPage.PageSize)]);
    }
}
