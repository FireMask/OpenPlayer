using System.Net.Sockets;
using System.Text;
using Microsoft.Extensions.Logging;
using OpenPlayer.Core.Commands;
using OpenPlayer.Core.Messages;
using OpenPlayer.Core.Models;
using OpenPlayer.Core.Tests;
using OpenPlayer.Mpd;

namespace OpenPlayer.Service.Tests;

public sealed class IpcServerTests : IAsyncLifetime
{
    private const int MaxBytes = 256;
    private const string GetSnapshot = """{"type":"player.get_snapshot"}""";

    private readonly DirectoryInfo _dir = Directory.CreateTempSubdirectory("op");
    private readonly FakePlayer _player = new();
    private readonly ListLogger _logger = new();
    private IpcServer _server = null!;

    private string SocketPath => Path.Combine(_dir.FullName, "h.sock");

    public Task InitializeAsync() => Task.CompletedTask;

    public async Task DisposeAsync()
    {
        await _server.StopAsync(CancellationToken.None);
        _server.Dispose();
        _dir.Delete(recursive: true);
    }

    private Task StartAsync()
    {
        _server = new IpcServer(new IpcOptions(SocketPath, MaxBytes), _player,
            new ButtonCommandHandler(_player, new PlayerSettings()), _logger);
        // ExecuteAsync corre síncrono hasta el primer AcceptAsync: al volver, el socket ya escucha.
        return _server.StartAsync(CancellationToken.None);
    }

    [Fact]
    public async Task Button_pressed_runs_button()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"button.pressed","button":"next","sequence":7}""" + "\n");
        await client.SendAsync(GetSnapshot + "\n");
        await client.ReadLineAsync();

        Assert.Equal(["Next", "GetSnapshot"], _player.Calls);
        Assert.Contains("Button Next (sequence 7)", _logger.Messages);
    }

    [Fact]
    public async Task Button_pressed_without_sequence_logs_only_button()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"button.pressed","button":"next"}""" + "\n");
        await client.SendAsync(GetSnapshot + "\n");
        await client.ReadLineAsync();

        Assert.Contains("Button Next", _logger.Messages);
        Assert.DoesNotContain(_logger.Messages, m => m.Contains("sequence"));
    }

    [Fact]
    public async Task Snapshot_request_replies_snapshot()
    {
        _player.Snapshot = new PlaybackSnapshot(PlaybackState.Playing,
            new Track("a.flac", "Canción", "Café Tacvba", null, null), TimeSpan.FromSeconds(42), null, 35,
            DateTimeOffset.UnixEpoch);
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync(GetSnapshot + "\n");

        Assert.Equal(SnapshotMessage.Serialize(_player.Snapshot), await client.ReadLineAsync());
    }

    [Fact]
    public async Task Mpd_failure_replies_error_and_keeps_connection()
    {
        _player.SnapshotError = new MpdUnavailableException("MPD down", new IOException());
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync(GetSnapshot + "\n");
        Assert.Equal("""{"type":"error","request":"player.get_snapshot","message":"MPD down"}""", await client.ReadLineAsync());

        _player.SnapshotError = null;
        await client.SendAsync(GetSnapshot + "\n");
        Assert.StartsWith("""{"type":"player.snapshot",""", await client.ReadLineAsync());
    }

    [Fact]
    public async Task Message_split_across_writes_is_processed()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"player.get_""");
        await Task.Delay(50);
        await client.SendAsync("snapshot\"}\r\n");

        Assert.StartsWith("""{"type":"player.snapshot",""", await client.ReadLineAsync());
    }

    [Fact]
    public async Task Two_messages_in_one_write_are_processed()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"button.pressed","button":"play_pause"}""" + "\n" + GetSnapshot + "\n");
        await client.ReadLineAsync();

        Assert.Equal(["TogglePlayback", "GetSnapshot"], _player.Calls);
    }

    [Fact]
    public async Task Invalid_json_keeps_connection()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("hola\n\n{\"type\":\"button.pressed\",\"button\":\"foo\"}\n" + GetSnapshot + "\n");

        Assert.StartsWith("""{"type":"player.snapshot",""", await client.ReadLineAsync());
        Assert.Equal(["GetSnapshot"], _player.Calls);
    }

    [Fact]
    public async Task Oversized_line_closes_only_that_connection()
    {
        await StartAsync();
        await using var other = await Client.ConnectAsync(SocketPath);
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync(new string('x', MaxBytes + 1));

        Assert.Null(await client.ReadLineAsync());
        await other.SendAsync(GetSnapshot + "\n");
        Assert.StartsWith("""{"type":"player.snapshot",""", await other.ReadLineAsync());
    }

    [Fact]
    public async Task Line_of_exactly_max_bytes_is_accepted()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);
        var prefix = GetSnapshot[..^1] + ",\"pad\":\"";
        var padded = prefix + new string('x', MaxBytes - prefix.Length - 2) + "\"}";

        Assert.Equal(MaxBytes, Encoding.UTF8.GetByteCount(padded));
        await client.SendAsync(padded + "\n");

        Assert.StartsWith("""{"type":"player.snapshot",""", await client.ReadLineAsync());
    }

    [Fact]
    public async Task Two_clients_each_get_their_reply()
    {
        await StartAsync();
        await using var a = await Client.ConnectAsync(SocketPath);
        await using var b = await Client.ConnectAsync(SocketPath);

        await a.SendAsync(GetSnapshot + "\n");
        await b.SendAsync(GetSnapshot + "\n");

        Assert.StartsWith("""{"type":"player.snapshot",""", await a.ReadLineAsync());
        Assert.StartsWith("""{"type":"player.snapshot",""", await b.ReadLineAsync());
        Assert.Equal(["GetSnapshot", "GetSnapshot"], _player.Calls);
    }

    [Fact]
    public async Task Starts_over_stale_socket_file()
    {
        await File.WriteAllTextAsync(SocketPath, "");
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync(GetSnapshot + "\n");

        Assert.StartsWith("""{"type":"player.snapshot",""", await client.ReadLineAsync());
    }

    [Fact]
    public async Task Stop_deletes_socket_file_with_client_connected()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);
        Assert.True(File.Exists(SocketPath));

        await _server.StopAsync(CancellationToken.None);

        Assert.False(File.Exists(SocketPath));
    }

    private sealed class ListLogger : ILogger<IpcServer>
    {
        private readonly System.Collections.Concurrent.ConcurrentQueue<string> _messages = new();

        public IReadOnlyCollection<string> Messages => _messages.ToArray();

        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception,
            Func<TState, Exception?, string> formatter) => _messages.Enqueue(formatter(state, exception));
    }

    private sealed class Client : IAsyncDisposable
    {
        private static readonly TimeSpan Timeout = TimeSpan.FromSeconds(5);
        private readonly NetworkStream _stream;
        private readonly StreamReader _reader;

        private Client(NetworkStream stream)
        {
            _stream = stream;
            _reader = new StreamReader(stream, Encoding.UTF8);
        }

        public static async Task<Client> ConnectAsync(string path)
        {
            var socket = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
            await socket.ConnectAsync(new UnixDomainSocketEndPoint(path)).WaitAsync(Timeout);
            return new Client(new NetworkStream(socket, ownsSocket: true));
        }

        public async Task SendAsync(string text) =>
            await _stream.WriteAsync(Encoding.UTF8.GetBytes(text)).AsTask().WaitAsync(Timeout);

        public async Task<string?> ReadLineAsync()
        {
            try
            {
                return await _reader.ReadLineAsync().WaitAsync(Timeout);
            }
            catch (IOException)
            {
                return null; // conexión cerrada por el servidor (reset)
            }
        }

        public async ValueTask DisposeAsync()
        {
            _reader.Dispose();
            await _stream.DisposeAsync();
        }
    }
}
