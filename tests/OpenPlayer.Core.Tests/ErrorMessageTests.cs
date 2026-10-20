using OpenPlayer.Core.Messages;

namespace OpenPlayer.Core.Tests;

public class ErrorMessageTests
{
    [Fact]
    public void Serializes_exactly()
    {
        Assert.Equal(
            """{"type":"error","request":"player.get_snapshot","message":"MPD did not respond within 3000 ms"}""",
            ErrorMessage.Serialize("player.get_snapshot", "MPD did not respond within 3000 ms"));
    }

    [Fact]
    public void Keeps_accents_and_escapes_quotes()
    {
        Assert.Equal(
            """{"type":"error","request":"player.get_snapshot","message":"Canción \"uno\" no válida"}""",
            ErrorMessage.Serialize("player.get_snapshot", "Canción \"uno\" no válida"));
    }
}
