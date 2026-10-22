namespace OpenPlayer.Core.Models;

/// <param name="Uri">Ruta relativa a la biblioteca MPD. Es un dato, nunca un comando.</param>
/// <param name="Track">null ⇔ carpeta.</param>
/// <param name="Id">Id de MPD en la cola (<c>playlistinfo</c>); null en biblioteca y playlists.</param>
public sealed record LibraryEntry(string Uri, Track? Track, int? Id = null);
