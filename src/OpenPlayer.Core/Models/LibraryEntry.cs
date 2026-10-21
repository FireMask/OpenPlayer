namespace OpenPlayer.Core.Models;

/// <param name="Uri">Ruta relativa a la biblioteca MPD. Es un dato, nunca un comando.</param>
/// <param name="Track">null ⇔ carpeta.</param>
public sealed record LibraryEntry(string Uri, Track? Track);
