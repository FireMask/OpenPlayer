using OpenPlayer.Core.Messages;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Tests;

public class LibraryMessagesTests
{
    [Fact]
    public void Ok_serializes_exactly() =>
        Assert.Equal("""{"type":"ok","request":"playlist.add"}""", OkMessage.Serialize("playlist.add"));

    [Fact]
    public void Playlist_list_serializes_exactly() =>
        Assert.Equal("""{"type":"playlist.list","playlists":["Viaje","Ñandú"]}""",
            PlaylistListMessage.Serialize(["Viaje", "Ñandú"]));

    [Fact]
    public void Library_page_serializes_directories_and_tracks_with_explicit_nulls()
    {
        var page = new LibraryPage(0, 2,
        [
            new LibraryEntry("Rock/AC DC", null),
            new LibraryEntry("Rock/x.mp3", new Track("Rock/x.mp3", "X", "A", null, TimeSpan.FromSeconds(210.7))),
        ]);

        Assert.Equal(
            """{"type":"library.page","offset":0,"total":2,"entries":[{"uri":"Rock/AC DC","directory":true},{"uri":"Rock/x.mp3","directory":false,"title":"X","artist":"A","album":null,"durationSeconds":210}]}""",
            LibraryPageMessage.Serialize(page));
    }

    [Fact]
    public void Library_page_serializes_empty() =>
        Assert.Equal("""{"type":"library.page","offset":100,"total":100,"entries":[]}""",
            LibraryPageMessage.Serialize(new LibraryPage(100, 100, [])));
}
