using OpenPlayer.Core.Messages;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Tests;

public class CoverMessageTests
{
    [Fact]
    public void Serializes_data_as_base64()
    {
        Assert.Equal(
            """{"type":"player.cover","songId":17,"mime":"image/png","data":"iVBORw=="}""",
            CoverMessage.Serialize(new Cover(17, "image/png", [0x89, 0x50, 0x4E, 0x47])));
    }

    [Fact]
    public void Serializes_nulls_explicitly()
    {
        Assert.Equal(
            """{"type":"player.cover","songId":null,"mime":null,"data":null}""",
            CoverMessage.Serialize(new Cover(null, null, null)));
    }
}
