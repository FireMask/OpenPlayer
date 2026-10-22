using OpenPlayer.Core.Messages;

namespace OpenPlayer.Core.Tests;

public class LibraryMessageParserTests
{
    public static TheoryData<string, IpcMessage> Valid => new()
    {
        { """{"type":"library.browse","path":"Rock/AC DC","offset":100}""", new LibraryBrowseRequested("Rock/AC DC", 100) },
        { """{"type":"library.browse","path":""}""", new LibraryBrowseRequested("", 0) },
        { """{"type":"library.search","query":"thunder","offset":0}""", new LibrarySearchRequested("thunder", 0) },
        { """{"type":"library.search","query":"ab"}""", new LibrarySearchRequested("ab", 0) },
        { """{"type":"library.play","uri":"Rock/AC DC/01.flac"}""", new LibraryPlayRequested("Rock/AC DC/01.flac") },
        { """{"type":"playlist.list"}""", new PlaylistListRequested() },
        { """{"type":"playlist.get","name":"Viaje","offset":0}""", new PlaylistGetRequested("Viaje", 0) },
        { """{"type":"playlist.get","name":"Viaje"}""", new PlaylistGetRequested("Viaje", 0) },
        { """{"type":"playlist.create","name":"Ñandú \"x\""}""", new PlaylistCreateRequested("Ñandú \"x\"") },
        { """{"type":"playlist.rename","name":"Viaje","newName":"Viaje 2026"}""", new PlaylistRenameRequested("Viaje", "Viaje 2026") },
        { """{"type":"playlist.delete","name":"Viaje"}""", new PlaylistDeleteRequested("Viaje") },
        { """{"type":"playlist.add","name":"Viaje","uri":"Rock/AC DC"}""", new PlaylistAddRequested("Viaje", "Rock/AC DC") },
        { """{"type":"playlist.remove","name":"Viaje","position":3}""", new PlaylistRemoveRequested("Viaje", 3) },
        { """{"type":"playlist.move","name":"Viaje","from":3,"to":2}""", new PlaylistMoveRequested("Viaje", 3, 2) },
        { """{"type":"playlist.play","name":"Viaje","position":4}""", new PlaylistPlayRequested("Viaje", 4) },
        { """{"type":"playlist.play","name":"Viaje"}""", new PlaylistPlayRequested("Viaje", 0) },
        { """{"type":"queue.get","offset":100}""", new QueueGetRequested(100) },
        { """{"type":"queue.get"}""", new QueueGetRequested(0) },
        { """{"type":"queue.play","position":3}""", new QueuePlayRequested(3) },
    };

    [Theory]
    [MemberData(nameof(Valid))]
    public void Parses_valid(string line, IpcMessage expected)
    {
        Assert.True(IpcMessageParser.TryParse(line, out var message, out var error, out var request));
        Assert.Equal(expected, message);
        Assert.Null(error);
        Assert.NotNull(request);
    }

    [Theory]
    [InlineData("""{"type":"playlist.get"}""", "playlist.get", "invalid name")]
    [InlineData("""{"type":"playlist.get","name":5}""", "playlist.get", "invalid name")]
    [InlineData("""{"type":"playlist.create","name":".x"}""", "playlist.create", "invalid name")]
    [InlineData("""{"type":"playlist.create","name":"a/b"}""", "playlist.create", "invalid name")]
    [InlineData("""{"type":"playlist.rename","name":"Viaje"}""", "playlist.rename", "invalid newName")]
    [InlineData("""{"type":"library.browse","path":"","offset":-1}""", "library.browse", "invalid offset")]
    [InlineData("""{"type":"library.browse","path":"","offset":"3"}""", "library.browse", "invalid offset")]
    [InlineData("""{"type":"library.browse","path":"","offset":3.5}""", "library.browse", "invalid offset")]
    [InlineData("""{"type":"library.browse"}""", "library.browse", "invalid path")]
    [InlineData("""{"type":"library.browse","path":"a\nb"}""", "library.browse", "invalid path")]
    [InlineData("""{"type":"library.search","query":"a"}""", "library.search", "invalid query")]
    [InlineData("""{"type":"library.play","uri":""}""", "library.play", "invalid uri")]
    [InlineData("""{"type":"playlist.add","name":"Viaje","uri":""}""", "playlist.add", "invalid uri")]
    [InlineData("""{"type":"playlist.remove","name":"Viaje"}""", "playlist.remove", "invalid position")]
    [InlineData("""{"type":"playlist.move","name":"Viaje","from":1}""", "playlist.move", "invalid to")]
    [InlineData("""{"type":"queue.get","offset":-1}""", "queue.get", "invalid offset")]
    [InlineData("""{"type":"queue.get","offset":"3"}""", "queue.get", "invalid offset")]
    [InlineData("""{"type":"queue.play"}""", "queue.play", "invalid position")]
    [InlineData("""{"type":"queue.play","position":-1}""", "queue.play", "invalid position")]
    [InlineData("""{"type":"queue.play","position":"3"}""", "queue.play", "invalid position")]
    [InlineData("""{"type":"queue.play","position":3.5}""", "queue.play", "invalid position")]
    public void Rejects_invalid_without_throwing_and_keeps_request(string line, string expectedRequest, string expectedError)
    {
        Assert.False(IpcMessageParser.TryParse(line, out var message, out var error, out var request));
        Assert.Null(message);
        Assert.Equal(expectedError, error);
        Assert.Equal(expectedRequest, request);
    }

    [Fact]
    public void Rejects_uri_longer_than_1024()
    {
        var line = $$"""{"type":"library.play","uri":"{{new string('a', 1025)}}"}""";
        Assert.False(IpcMessageParser.TryParse(line, out _, out var error, out _));
        Assert.Equal("invalid uri", error);
    }

    [Theory]
    [InlineData("""{"type":"player.seek"}""")]
    [InlineData("""{"type":"library.unknown"}""")]
    public void Request_is_null_for_types_without_reply(string line)
    {
        Assert.False(IpcMessageParser.TryParse(line, out _, out _, out var request));
        Assert.Null(request);
    }
}
