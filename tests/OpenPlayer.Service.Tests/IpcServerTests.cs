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
    private readonly FakeLibrary _library = new();
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
            new ButtonCommandHandler(_player, new PlayerSettings()), _library, _library, _library, _logger);
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
    public async Task Seek_runs_seek_without_reply()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"player.seek","positionSeconds":83}""" + "\n");
        await client.SendAsync(GetSnapshot + "\n");

        // La primera línea recibida es la del snapshot: el seek no respondió nada.
        Assert.StartsWith("""{"type":"player.snapshot",""", await client.ReadLineAsync());
        Assert.Equal(["Seek(00:01:23)", "GetSnapshot"], _player.Calls);
        Assert.Contains("Seek to 83 s", _logger.Messages);
    }

    [Fact]
    public async Task Seek_failure_keeps_connection()
    {
        _player.SeekError = new MpdException("seekcur", "Not playing");
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"player.seek","positionSeconds":83}""" + "\n");
        await client.SendAsync(GetSnapshot + "\n");

        Assert.StartsWith("""{"type":"player.snapshot",""", await client.ReadLineAsync());
        Assert.Contains("Seek failed: Not playing", _logger.Messages);
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

    [Theory]
    [InlineData("""{"type":"library.play","uri":"Rock/a.mp3"}""", "PlayTrack(Rock/a.mp3)", "library.play")]
    [InlineData("""{"type":"playlist.create","name":"Viaje"}""", "Create(Viaje)", "playlist.create")]
    [InlineData("""{"type":"playlist.rename","name":"Viaje","newName":"Gym 2"}""", "Rename(Viaje,Gym 2)", "playlist.rename")]
    [InlineData("""{"type":"playlist.delete","name":"Viaje"}""", "Delete(Viaje)", "playlist.delete")]
    [InlineData("""{"type":"playlist.add","name":"Viaje","uri":"Rock"}""", "Add(Viaje,Rock)", "playlist.add")]
    [InlineData("""{"type":"playlist.remove","name":"Viaje","position":3}""", "Remove(Viaje,3)", "playlist.remove")]
    [InlineData("""{"type":"playlist.move","name":"Viaje","from":3,"to":2}""", "Move(Viaje,3,2)", "playlist.move")]
    [InlineData("""{"type":"playlist.play","name":"Viaje","position":4}""", "Play(Viaje,4)", "playlist.play")]
    [InlineData("""{"type":"queue.play","position":3}""", "QueuePlay(3)", "queue.play")]
    [InlineData("""{"type":"queue.remove","id":17}""", "QueueRemove(17)", "queue.remove")]
    [InlineData("""{"type":"queue.move","id":17,"to":2}""", "QueueMove(17,2)", "queue.move")]
    [InlineData("""{"type":"queue.clear"}""", "QueueClear", "queue.clear")]
    [InlineData("""{"type":"queue.add","uri":"a.flac","next":true}""", "QueueAdd(a.flac,True)", "queue.add")]
    [InlineData("""{"type":"queue.add","uri":"Rock"}""", "QueueAdd(Rock,False)", "queue.add")]
    [InlineData("""{"type":"queue.save","name":"Viaje"}""", "QueueSave(Viaje)", "queue.save")]
    public async Task Mutation_calls_store_and_replies_ok(string line, string expectedCall, string request)
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync(line + "\n");

        Assert.Equal(OkMessage.Serialize(request), await client.ReadLineAsync());
        Assert.Equal([expectedCall], _library.Calls);
    }

    [Theory]
    [InlineData("""{"type":"library.browse","path":"","offset":100}""", "Browse(,100)")]
    [InlineData("""{"type":"library.search","query":"thunder"}""", "Search(thunder,0)")]
    [InlineData("""{"type":"playlist.get","name":"Viaje"}""", "Get(Viaje,0)")]
    public async Task Query_replies_library_page(string line, string expectedCall)
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync(line + "\n");

        Assert.Equal(LibraryPageMessage.Serialize(_library.Page), await client.ReadLineAsync());
        Assert.Equal([expectedCall], _library.Calls);
    }

    [Fact]
    public async Task Playlist_list_replies_names()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"playlist.list"}""" + "\n");

        Assert.Equal("""{"type":"playlist.list","playlists":["Viaje","Gym"]}""", await client.ReadLineAsync());
    }

    [Fact]
    public async Task Store_failure_replies_error_and_keeps_connection()
    {
        _library.Error = new MpdException("rm \"Nope\"", "No such playlist");
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"playlist.delete","name":"Nope"}""" + "\n");
        Assert.Equal("""{"type":"error","request":"playlist.delete","message":"No such playlist"}""", await client.ReadLineAsync());

        _library.Error = null;
        await client.SendAsync("""{"type":"playlist.list"}""" + "\n");
        Assert.StartsWith("""{"type":"playlist.list",""", await client.ReadLineAsync());
        Assert.Contains("playlist.delete failed: No such playlist", _logger.Messages);
    }

    [Fact]
    public async Task Invalid_new_message_replies_error_and_keeps_connection()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"playlist.create","name":"a/b"}""" + "\n");
        Assert.Equal("""{"type":"error","request":"playlist.create","message":"invalid name"}""", await client.ReadLineAsync());

        await client.SendAsync("""{"type":"playlist.list"}""" + "\n");
        Assert.StartsWith("""{"type":"playlist.list",""", await client.ReadLineAsync());
        Assert.DoesNotContain(_library.Calls, c => c.StartsWith("Create"));
    }

    [Fact]
    public async Task Queue_get_replies_queue_page_without_playlist_at_start()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"queue.get","offset":100}""" + "\n");

        Assert.Equal(QueuePageMessage.Serialize(_library.Page, null), await client.ReadLineAsync());
        Assert.Equal(["QueueGet(100)"], _library.Calls);
        Assert.Contains("queue.get ok (offset 100)", _logger.Messages);
    }

    [Fact]
    public async Task Loaded_playlist_follows_play_rename_and_delete()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        async Task Send(string line)
        {
            await client.SendAsync(line + "\n");
            Assert.StartsWith("""{"type":"ok",""", await client.ReadLineAsync());
        }
        async Task<string?> LoadedPlaylist()
        {
            await client.SendAsync("""{"type":"queue.get"}""" + "\n");
            using var doc = System.Text.Json.JsonDocument.Parse((await client.ReadLineAsync())!);
            return doc.RootElement.GetProperty("playlist").GetString();
        }

        await Send("""{"type":"playlist.play","name":"Viaje"}""");
        Assert.Equal("Viaje", await LoadedPlaylist());

        await Send("""{"type":"playlist.rename","name":"Otra","newName":"Otra 2"}""");
        Assert.Equal("Viaje", await LoadedPlaylist());

        await Send("""{"type":"playlist.rename","name":"Viaje","newName":"Gym"}""");
        Assert.Equal("Gym", await LoadedPlaylist());

        await Send("""{"type":"playlist.delete","name":"Otra 2"}""");
        Assert.Equal("Gym", await LoadedPlaylist());

        await Send("""{"type":"playlist.delete","name":"Gym"}""");
        Assert.Null(await LoadedPlaylist());

        await Send("""{"type":"playlist.play","name":"Viaje"}""");
        await Send("""{"type":"library.play","uri":"Rock/a.mp3"}""");
        Assert.Null(await LoadedPlaylist());

        // SPEC 12: quitar y mover no cambian el nombre; limpiar lo borra.
        await Send("""{"type":"playlist.play","name":"Viaje"}""");
        await Send("""{"type":"queue.remove","id":17}""");
        await Send("""{"type":"queue.move","id":18,"to":0}""");
        Assert.Equal("Viaje", await LoadedPlaylist());
        await Send("""{"type":"queue.clear"}""");
        Assert.Null(await LoadedPlaylist());

        // SPEC 13: agregar no cambia el nombre; guardar lo fija.
        await Send("""{"type":"playlist.play","name":"Viaje"}""");
        await Send("""{"type":"queue.add","uri":"a.flac","next":true}""");
        await Send("""{"type":"queue.add","uri":"Rock"}""");
        Assert.Equal("Viaje", await LoadedPlaylist());
        await Send("""{"type":"queue.save","name":"Gym"}""");
        Assert.Equal("Gym", await LoadedPlaylist());
    }

    [Fact]
    public async Task Failed_queue_save_keeps_loaded_playlist()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"playlist.play","name":"Viaje"}""" + "\n");
        await client.ReadLineAsync();
        _library.Error = new MpdException("save \"Gym\"", "Playlist already exists");
        await client.SendAsync("""{"type":"queue.save","name":"Gym"}""" + "\n");
        Assert.Equal("""{"type":"error","request":"queue.save","message":"Playlist already exists"}""", await client.ReadLineAsync());

        _library.Error = null;
        await client.SendAsync("""{"type":"queue.get"}""" + "\n");
        Assert.StartsWith("""{"type":"queue.page","playlist":"Viaje",""", await client.ReadLineAsync());
    }

    [Fact]
    public async Task Failed_queue_clear_keeps_loaded_playlist()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"playlist.play","name":"Viaje"}""" + "\n");
        await client.ReadLineAsync();
        _library.Error = new MpdUnavailableException("MPD down", new IOException());
        await client.SendAsync("""{"type":"queue.clear"}""" + "\n");
        Assert.StartsWith("""{"type":"error","request":"queue.clear",""", await client.ReadLineAsync());

        _library.Error = null;
        await client.SendAsync("""{"type":"queue.get"}""" + "\n");
        Assert.StartsWith("""{"type":"queue.page","playlist":"Viaje",""", await client.ReadLineAsync());
    }

    [Fact]
    public async Task Failed_playlist_play_keeps_loaded_playlist()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"playlist.play","name":"Viaje"}""" + "\n");
        await client.ReadLineAsync();
        _library.Error = new MpdException("load \"Nope\"", "No such playlist");
        await client.SendAsync("""{"type":"playlist.play","name":"Nope"}""" + "\n");
        Assert.StartsWith("""{"type":"error","request":"playlist.play",""", await client.ReadLineAsync());

        _library.Error = null;
        await client.SendAsync("""{"type":"queue.get"}""" + "\n");
        Assert.StartsWith("""{"type":"queue.page","playlist":"Viaje",""", await client.ReadLineAsync());
    }

    [Theory]
    [InlineData("""{"type":"queue.get"}""", "queue.get")]
    [InlineData("""{"type":"queue.play","position":99}""", "queue.play")]
    [InlineData("""{"type":"queue.remove","id":99}""", "queue.remove")]
    [InlineData("""{"type":"queue.move","id":99,"to":0}""", "queue.move")]
    [InlineData("""{"type":"queue.clear"}""", "queue.clear")]
    [InlineData("""{"type":"queue.add","uri":"nope.flac"}""", "queue.add")]
    public async Task Queue_failure_replies_error_and_keeps_connection(string line, string request)
    {
        _library.Error = new MpdException("play 99", "Bad song index");
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync(line + "\n");
        Assert.Equal($$"""{"type":"error","request":"{{request}}","message":"Bad song index"}""", await client.ReadLineAsync());

        _library.Error = null;
        await client.SendAsync("""{"type":"playlist.list"}""" + "\n");
        Assert.StartsWith("""{"type":"playlist.list",""", await client.ReadLineAsync());
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
