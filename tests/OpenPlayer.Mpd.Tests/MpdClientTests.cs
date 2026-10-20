using System.Net;
using System.Net.Sockets;

namespace OpenPlayer.Mpd.Tests;

public class MpdClientTests
{
    private static readonly CancellationToken Ct = CancellationToken.None;

    [Fact]
    public async Task Sends_commands_in_one_connection_and_parses_pairs()
    {
        await using var server = new FakeMpdServer
        {
            Respond = c => c == "status" ? "volume: 35\nstate: play\nOK\n" : "file: a.mp3\nTitle: A: B\nOK\n",
        };

        var responses = await new MpdClient(server.Options()).ExecuteAsync(["status", "currentsong"], Ct);
        await server.AllClosed();

        Assert.Equal([["status", "currentsong"]], server.Connections);
        Assert.Equal("35", responses[0].Get("volume"));
        Assert.Equal("play", responses[0].Get("state"));
        Assert.Equal("A: B", responses[1].Get("Title"));
    }

    [Fact]
    public async Task Each_call_opens_its_own_connection()
    {
        await using var server = new FakeMpdServer();
        var client = new MpdClient(server.Options());

        await client.ExecuteAsync(["next"], Ct);
        await client.ExecuteAsync(["previous"], Ct);
        await server.AllClosed();

        Assert.Equal([["next"], ["previous"]], server.Connections);
    }

    [Fact]
    public async Task Ack_throws_MpdException_and_closes()
    {
        await using var server = new FakeMpdServer { Respond = _ => "ACK [2@0] {seekcur} Not playing\n" };

        var e = await Assert.ThrowsAsync<MpdException>(
            () => new MpdClient(server.Options()).ExecuteAsync(["seekcur 0"], Ct));
        await server.AllClosed();

        Assert.Equal("seekcur 0", e.Command);
        Assert.Contains("Not playing", e.Message);
    }

    [Fact]
    public async Task Closed_port_throws_unavailable()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();

        // Windows reintenta el SYN ~2 s antes de rechazar; el timeout cubre ese caso igual.
        var client = new MpdClient(new MpdOptions("127.0.0.1", port, TimeSpan.FromMilliseconds(500)));

        await Assert.ThrowsAsync<MpdUnavailableException>(() => client.ExecuteAsync(["status"], Ct));
    }

    [Fact]
    public async Task Invalid_greeting_throws_unavailable_and_closes()
    {
        await using var server = new FakeMpdServer { Greeting = "HELLO" };

        await Assert.ThrowsAsync<MpdUnavailableException>(
            () => new MpdClient(server.Options()).ExecuteAsync(["status"], Ct));
        await server.AllClosed();
    }

    [Fact]
    public async Task Silent_server_times_out_as_unavailable_and_closes()
    {
        await using var server = new FakeMpdServer { Greeting = null };

        await Assert.ThrowsAsync<MpdUnavailableException>(
            () => new MpdClient(server.Options(timeoutMs: 200)).ExecuteAsync(["status"], Ct));
        await server.AllClosed();
    }

    [Theory]
    [InlineData("")]
    [InlineData("play\nclear")]
    [InlineData("play\r")]
    public async Task Rejects_invalid_commands_without_connecting(string command)
    {
        await using var server = new FakeMpdServer();

        await Assert.ThrowsAsync<ArgumentException>(
            () => new MpdClient(server.Options()).ExecuteAsync([command], Ct));

        Assert.Empty(server.Connections);
    }
}
