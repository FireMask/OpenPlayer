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

    [Fact]
    public void Queue_page_serializes_exactly()
    {
        var page = new LibraryPage(0, 2,
        [
            new LibraryEntry("A1.flac", new Track("A1.flac", "Rolling In The Deep", "Adele", "21", TimeSpan.FromSeconds(225.4)), 17),
            new LibraryEntry("x.mp3", new Track("x.mp3", null, null, null, null)),
        ]);

        Assert.Equal(
            """{"type":"queue.page","playlist":"Favoritas","offset":0,"total":2,"entries":[{"uri":"A1.flac","id":17,"title":"Rolling In The Deep","artist":"Adele","album":"21","durationSeconds":225},{"uri":"x.mp3","id":null,"title":null,"artist":null,"album":null,"durationSeconds":null}]}""",
            QueuePageMessage.Serialize(page, "Favoritas"));
    }

    [Fact]
    public void Queue_page_serializes_null_playlist() =>
        Assert.Equal("""{"type":"queue.page","playlist":null,"offset":0,"total":0,"entries":[]}""",
            QueuePageMessage.Serialize(new LibraryPage(0, 0, []), null));
}
