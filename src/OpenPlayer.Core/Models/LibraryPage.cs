namespace OpenPlayer.Core.Models;

/// <summary>Una página de entradas; en playlists, la posición de cada pista es <c>Offset + índice</c>.</summary>
public sealed record LibraryPage(int Offset, int Total, IReadOnlyList<LibraryEntry> Entries)
{
    public const int PageSize = 100;
}
