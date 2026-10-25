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
    private readonly FakePowerControl _power = new();
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

    private async Task StartAsync()
    {
        _server = new IpcServer(new IpcOptions(SocketPath, MaxBytes), _player,
            new ButtonCommandHandler(_player, new PlayerSettings()), new PlayerSettings(), _library, _library, _library, _power, _logger);
        // ExecuteAsync corre síncrono hasta el primer AcceptAsync: al volver, el socket ya escucha.
        await _server.StartAsync(CancellationToken.None);
        // El observador lee un snapshot al arrancar: esperar a que quede en idle y olvidar esa llamada.
        if (_player.SnapshotError is null)
        {
            await _player.Waiting.Task.WaitAsync(TimeSpan.FromSeconds(5));
            _player.Calls.Clear();
        }
    }

    private static PlaybackSnapshot Song(string uri, int id, PlaybackState state = PlaybackState.Playing) =>
        new(state, new Track(uri, null, null, null, null), TimeSpan.Zero, null, null, DateTimeOffset.UnixEpoch, SongId: id);

    // Simula que MPD pasó a esa canción y espera a que el observador lo procese.
    private Task PlayingAsync(string uri, int id, PlaybackState state = PlaybackState.Playing)
    {
        _player.Snapshot = Song(uri, id, state);
        return _player.ChangeAsync();
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
    public async Task Power_off_logs_and_powers_off_without_touching_mpd()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"button.pressed","button":"power_off","sequence":14}""" + "\n");
        await client.SendAsync(GetSnapshot + "\n");
        await client.ReadLineAsync();

        Assert.Equal(1, _power.Calls);
        Assert.Equal(["GetSnapshot"], _player.Calls);
        Assert.Contains("Power off requested (button)", _logger.Messages);
    }

    [Fact]
    public async Task Power_off_failure_logs_and_keeps_serving()
    {
        _power.Error = new InvalidOperationException("Access denied");
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"button.pressed","button":"power_off"}""" + "\n");
        await client.SendAsync(GetSnapshot + "\n");

        Assert.StartsWith("""{"type":"player.snapshot",""", await client.ReadLineAsync());
        Assert.Contains("Power off failed: Access denied", _logger.Messages);
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
    public async Task Queue_get_replies_queue_page_without_sources_at_start()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync("""{"type":"queue.get","offset":100}""" + "\n");

        Assert.Equal(QueuePageMessage.Serialize(_library.Page, new Dictionary<int, string>()), await client.ReadLineAsync());
        Assert.Equal(["QueueGet(100)"], _library.Calls);
        Assert.Contains("queue.get ok (offset 100)", _logger.Messages);
    }

    // SPEC 14: etiqueta de origen por id de MPD, leída de queue.get.
    private async Task<Dictionary<int, string?>> Sources(Client client)
    {
        await client.SendAsync("""{"type":"queue.get"}""" + "\n");
        using var doc = System.Text.Json.JsonDocument.Parse((await client.ReadLineAsync())!);
        return doc.RootElement.GetProperty("entries").EnumerateArray()
            .ToDictionary(e => e.GetProperty("id").GetInt32(), e => e.GetProperty("source").GetString());
    }

    private static async Task SendOk(Client client, string line)
    {
        await client.SendAsync(line + "\n");
        Assert.StartsWith("""{"type":"ok",""", await client.ReadLineAsync());
    }

    // La página de la fake devuelve estas entradas en queue.get.
    private void QueueOf(params int[] ids)
    {
        _library.Ids = [.. ids];
        _library.Page = new LibraryPage(0, ids.Length, [.. ids.Select(id => new LibraryEntry($"{id}.flac", null, id))]);
    }

    [Fact]
    public async Task Sources_follow_play_add_and_clear()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        QueueOf(1, 2);
        await SendOk(client, """{"type":"playlist.play","name":"Viaje"}""");
        Assert.Equal(new Dictionary<int, string?> { [1] = "Viaje", [2] = "Viaje" }, await Sources(client));

        await SendOk(client, """{"type":"queue.add","uri":"a.flac"}""");      // id 3
        await SendOk(client, """{"type":"queue.add","uri":"b.flac","next":true}""");  // id 4
        QueueOf([.. _library.Ids]);
        Assert.Equal(new Dictionary<int, string?> { [1] = "Viaje", [2] = "Viaje", [3] = "Biblioteca", [4] = "Biblioteca" },
            await Sources(client));

        await SendOk(client, """{"type":"playlist.rename","name":"Viaje","newName":"Gym"}""");
        await SendOk(client, """{"type":"queue.save","name":"Otra"}""");
        await SendOk(client, """{"type":"playlist.delete","name":"Gym"}""");
        Assert.Equal("Viaje", (await Sources(client))[1]);

        await SendOk(client, """{"type":"queue.clear"}""");
        Assert.All((await Sources(client)).Values, Assert.Null);

        QueueOf(7);
        await SendOk(client, """{"type":"library.play","uri":"Rock/a.mp3"}""");
        Assert.Equal(new Dictionary<int, string?> { [7] = "Biblioteca" }, await Sources(client));
    }

    [Fact]
    public async Task Add_drops_sources_of_songs_no_longer_in_queue()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        QueueOf(1, 2);
        await SendOk(client, """{"type":"playlist.play","name":"Viaje"}""");
        _library.Ids.Remove(1);  // consumida
        await SendOk(client, """{"type":"queue.add","uri":"a.flac"}""");  // id 3
        QueueOf(1, 2, 3);  // la página vieja incluye la 1 para ver que perdió la etiqueta

        Assert.Equal(new Dictionary<int, string?> { [1] = null, [2] = "Viaje", [3] = "Biblioteca" }, await Sources(client));
    }

    [Fact]
    public async Task Failed_add_keeps_sources()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        QueueOf(1);
        await SendOk(client, """{"type":"playlist.play","name":"Viaje"}""");
        _library.Error = new MpdException("add \"x\"", "No such directory");
        await client.SendAsync("""{"type":"queue.add","uri":"x"}""" + "\n");
        Assert.StartsWith("""{"type":"error","request":"queue.add",""", await client.ReadLineAsync());

        _library.Error = null;
        Assert.Equal(new Dictionary<int, string?> { [1] = "Viaje" }, await Sources(client));
    }

    [Fact]
    public async Task Ids_failure_after_add_still_replies_ok_without_label()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        _library.IdsError = new MpdUnavailableException("MPD down", new IOException());
        await SendOk(client, """{"type":"queue.add","uri":"a.flac"}""");
        _library.IdsError = null;
        QueueOf(1);

        Assert.Equal(new Dictionary<int, string?> { [1] = null }, await Sources(client));
        Assert.Contains(_logger.Messages, m => m.StartsWith("queue ids failed"));
    }

    [Fact]
    public async Task Start_enables_consume()
    {
        await StartAsync();
        // ExecuteAsync corre en segundo plano: esperar a que active consume.
        for (var i = 0; i < 100 && !_logger.Messages.Contains("consume on"); i++)
            await Task.Delay(10);

        Assert.Equal(1, _library.ConsumeCalls);
        Assert.Contains("consume on", _logger.Messages);
    }

    [Fact]
    public async Task Start_with_mpd_down_logs_consume_warning_and_serves()
    {
        _library.Error = new MpdUnavailableException("MPD down", new IOException());
        _player.SnapshotError = new MpdUnavailableException("MPD down", new IOException());
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync(GetSnapshot + "\n");

        Assert.StartsWith("""{"type":"error","request":"player.get_snapshot",""", await client.ReadLineAsync());
        Assert.Contains(_logger.Messages, m => m.StartsWith("consume failed"));
        for (var i = 0; i < 100 && !_logger.Messages.Any(m => m.StartsWith("player watch failed")); i++)
            await Task.Delay(10);
        Assert.Contains(_logger.Messages, m => m.StartsWith("player watch failed"));
    }

    [Theory]
    [InlineData(PlaybackState.Playing, true)]
    [InlineData(PlaybackState.Paused, true)]
    [InlineData(PlaybackState.Stopped, false)]
    public async Task Song_change_adds_previous_song_only_if_it_played(PlaybackState state, bool added)
    {
        await StartAsync();

        await PlayingAsync("a.flac", 1, state);
        await PlayingAsync("b.flac", 2);

        Assert.Equal(added ? [new IpcServer.PlayedSong("a.flac", null)] : [], _server.History);
    }

    [Fact]
    public async Task Stopped_song_that_starts_playing_counts_as_played()
    {
        await StartAsync();

        await PlayingAsync("a.flac", 1, PlaybackState.Stopped);
        await PlayingAsync("a.flac", 1);
        await PlayingAsync("b.flac", 2);

        Assert.Equal([new IpcServer.PlayedSong("a.flac", null)], _server.History);
    }

    [Fact]
    public async Task History_keeps_the_label_even_after_the_queue_is_relabeled()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);
        QueueOf(1);
        await SendOk(client, """{"type":"playlist.play","name":"Viaje"}""");
        await PlayingAsync("a.flac", 1);

        _library.Ids = [2];
        await SendOk(client, """{"type":"library.play","uri":"b.flac"}""");
        await PlayingAsync("b.flac", 2);

        Assert.Equal([new IpcServer.PlayedSong("a.flac", "Viaje")], _server.History);
    }

    [Fact]
    public async Task Same_song_or_seek_does_not_add_to_history()
    {
        await StartAsync();

        await PlayingAsync("a.flac", 1);
        await PlayingAsync("a.flac", 1, PlaybackState.Paused);

        Assert.Empty(_server.History);
    }

    [Fact]
    public async Task History_keeps_the_last_50()
    {
        await StartAsync();

        for (var i = 0; i <= 51; i++)
            await PlayingAsync($"t{i}.flac", i + 1);

        Assert.Equal(50, _server.History.Count);
        Assert.Equal("t1.flac", _server.History[0].Uri);
        Assert.Equal("t50.flac", _server.History[^1].Uri);
    }

    private const string Previous = """{"type":"button.pressed","button":"previous"}""";

    // Viaje: a (id 1) sonó y pasó a b (id 2); el historial queda [a/Viaje].
    private async Task<Client> AfterOneSongAsync()
    {
        await StartAsync();
        var client = await Client.ConnectAsync(SocketPath);
        QueueOf(1, 2);
        await SendOk(client, """{"type":"playlist.play","name":"Viaje"}""");
        await PlayingAsync("a.flac", 1);
        QueueOf(2);
        await PlayingAsync("b.flac", 2);
        _player.Calls.Clear();
        return client;
    }

    // button.pressed no responde: un get_snapshot después marca que ya se procesó.
    private static async Task PressAsync(Client client, string button)
    {
        await client.SendAsync(button + "\n" + GetSnapshot + "\n");
        await client.ReadLineAsync();
    }

    [Fact]
    public async Task Previous_with_history_restores_last_song_on_top_with_its_label()
    {
        await using var client = await AfterOneSongAsync();
        _player.Snapshot = _player.Snapshot with { Position = TimeSpan.FromSeconds(2) };

        await PressAsync(client, Previous);

        Assert.Contains("QueueRestore(a.flac)", _library.Calls);
        Assert.Empty(_server.History);
        Assert.DoesNotContain("Previous", _player.Calls);
        QueueOf([.. _library.Ids]);
        Assert.Equal("Viaje", (await Sources(client))[_library.Ids[0]]);
    }

    [Fact]
    public async Task Previous_with_unknown_position_restores()
    {
        await using var client = await AfterOneSongAsync();
        _player.Snapshot = _player.Snapshot with { Position = null };

        await PressAsync(client, Previous);

        Assert.Contains("QueueRestore(a.flac)", _library.Calls);
    }

    [Fact]
    public async Task Previous_past_threshold_restarts_and_keeps_history()
    {
        await using var client = await AfterOneSongAsync();
        _player.Snapshot = _player.Snapshot with { Position = TimeSpan.FromSeconds(4) };

        await PressAsync(client, Previous);

        Assert.DoesNotContain(_library.Calls, c => c.StartsWith("QueueRestore"));
        Assert.Contains("Seek(00:00:00)", _player.Calls);
        Assert.Single(_server.History);
    }

    [Fact]
    public async Task Previous_without_history_restarts_as_before()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);
        _player.Snapshot = Song("a.flac", 1);

        await PressAsync(client, Previous);

        Assert.DoesNotContain(_library.Calls, c => c.StartsWith("QueueRestore"));
        Assert.Contains("Previous", _player.Calls);
    }

    [Fact]
    public async Task Previous_twice_goes_back_two_songs_without_bouncing()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);
        await PlayingAsync("a.flac", 1);
        await PlayingAsync("b.flac", 2);
        await PlayingAsync("c.flac", 3);
        _library.Ids = [3];

        await PressAsync(client, Previous);
        await PlayingAsync("b.flac", _library.Ids[0]);   // MPD avisa que ahora suena la restaurada
        await PressAsync(client, Previous);
        await PlayingAsync("a.flac", _library.Ids[0]);

        Assert.Equal(["QueueRestore(b.flac)", "QueueRestore(a.flac)"],
            _library.Calls.Where(c => c.StartsWith("QueueRestore")));
        Assert.Empty(_server.History);
    }

    [Fact]
    public async Task Restored_song_returns_to_history_when_it_ends()
    {
        await using var client = await AfterOneSongAsync();

        await PressAsync(client, Previous);
        await PlayingAsync("a.flac", _library.Ids[0]);
        await PlayingAsync("b.flac", 2);

        Assert.Equal([new IpcServer.PlayedSong("a.flac", "Viaje")], _server.History);
    }

    [Fact]
    public async Task Previous_with_missing_file_drops_entry_and_restarts()
    {
        await using var client = await AfterOneSongAsync();
        _library.Error = new MpdException("add \"a.flac\" 0", "No such directory");

        await PressAsync(client, Previous);

        Assert.Empty(_server.History);
        Assert.Contains("Previous", _player.Calls);
        Assert.Contains(_logger.Messages, m => m.StartsWith("restore a.flac failed"));
    }

    [Fact]
    public async Task Queue_ending_adds_the_last_song()
    {
        await StartAsync();

        await PlayingAsync("a.flac", 1);
        _player.Snapshot = new PlaybackSnapshot(PlaybackState.Stopped, null, null, null, null, DateTimeOffset.UnixEpoch);
        await _player.ChangeAsync();

        Assert.Equal([new IpcServer.PlayedSong("a.flac", null)], _server.History);
    }

    private const string Subscribe = """{"type":"player.subscribe"}""";

    private async Task<Client> SubscribeAsync()
    {
        var client = await Client.ConnectAsync(SocketPath);
        await client.SendAsync(Subscribe + "\n");
        return client;
    }

    [Fact]
    public async Task Subscribe_replies_current_snapshot_at_once()
    {
        _player.Snapshot = Song("a.flac", 1);
        await StartAsync();
        await using var client = await SubscribeAsync();

        Assert.Equal(SnapshotMessage.Serialize(_player.Snapshot), await client.ReadLineAsync());
        Assert.Equal(1, _server.SubscriberCount);
        Assert.Contains("player.subscribe", _logger.Messages);
    }

    [Fact]
    public async Task Change_pushes_snapshot_to_every_subscriber()
    {
        await StartAsync();
        await using var a = await SubscribeAsync();
        await using var b = await SubscribeAsync();
        await a.ReadLineAsync();
        await b.ReadLineAsync();

        await PlayingAsync("b.flac", 2);

        var pushed = SnapshotMessage.Serialize(Song("b.flac", 2));
        Assert.Equal(pushed, await a.ReadLineAsync());
        Assert.Equal(pushed, await b.ReadLineAsync());
    }

    [Fact]
    public async Task Subscribed_connection_ignores_further_requests_and_others_still_reply()
    {
        await StartAsync();
        await using var sub = await SubscribeAsync();
        await sub.ReadLineAsync();
        await using var other = await Client.ConnectAsync(SocketPath);

        await sub.SendAsync(GetSnapshot + "\n");
        await other.SendAsync(GetSnapshot + "\n");
        Assert.StartsWith("""{"type":"player.snapshot",""", await other.ReadLineAsync());
        await PlayingAsync("b.flac", 2);

        // La siguiente línea es el push, no una respuesta al get_snapshot ignorado.
        Assert.Equal(SnapshotMessage.Serialize(Song("b.flac", 2)), await sub.ReadLineAsync());
    }

    [Fact]
    public async Task Mpd_failure_in_observer_pushes_error_line()
    {
        await StartAsync();
        await using var client = await SubscribeAsync();
        await client.ReadLineAsync();

        _player.SnapshotError = new MpdUnavailableException("MPD down", new IOException());
        _ = _player.ChangeAsync(); // el observador queda reintentando: no vuelve a esperar enseguida

        Assert.Equal("""{"type":"error","request":"player.get_snapshot","message":"MPD down"}""", await client.ReadLineAsync());
    }

    [Fact]
    public async Task Subscribe_with_mpd_down_replies_error_and_stays_subscribed()
    {
        _player.SnapshotError = new MpdUnavailableException("MPD down", new IOException());
        await StartAsync();
        await using var client = await SubscribeAsync();

        Assert.StartsWith("""{"type":"error","request":"player.get_snapshot",""", await client.ReadLineAsync());
        Assert.Equal(1, _server.SubscriberCount);
    }

    [Fact]
    public async Task Closed_subscriber_is_removed_and_others_keep_receiving()
    {
        await StartAsync();
        var gone = await SubscribeAsync();
        await using var stays = await SubscribeAsync();
        await gone.ReadLineAsync();
        await stays.ReadLineAsync();

        await gone.DisposeAsync();
        for (var i = 0; i < 100 && _server.SubscriberCount > 1; i++)
            await Task.Delay(10);
        Assert.Equal(1, _server.SubscriberCount);

        await PlayingAsync("b.flac", 2);
        Assert.Equal(SnapshotMessage.Serialize(Song("b.flac", 2)), await stays.ReadLineAsync());
    }

    private const string Menu = """{"type":"button.pressed","button":"menu"}""";

    [Fact]
    public async Task Display_mode_starts_as_track()
    {
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync(GetSnapshot + "\n");

        Assert.EndsWith(""","displayMode":"track"}""", await client.ReadLineAsync());
    }

    [Fact]
    public async Task Menu_cycles_track_clock_art_and_pushes_without_touching_mpd()
    {
        _player.Snapshot = Song("a.flac", 1);
        await StartAsync();
        await using var a = await SubscribeAsync();
        await using var b = await SubscribeAsync();
        await a.ReadLineAsync();
        await b.ReadLineAsync();
        await using var buttons = await Client.ConnectAsync(SocketPath);
        _player.Calls.Clear();

        await buttons.SendAsync(Menu + "\n");
        var clock = SnapshotMessage.Serialize(_player.Snapshot, "clock");
        Assert.Equal(clock, await a.ReadLineAsync());
        Assert.Equal(clock, await b.ReadLineAsync());

        await buttons.SendAsync(Menu + "\n");
        Assert.Equal(SnapshotMessage.Serialize(_player.Snapshot, "art"), await a.ReadLineAsync());
        await buttons.SendAsync(Menu + "\n");
        Assert.Equal(SnapshotMessage.Serialize(_player.Snapshot, "track"), await a.ReadLineAsync());
        Assert.Equal(["GetSnapshot", "GetSnapshot", "GetSnapshot"], _player.Calls);
        Assert.Contains("Display mode clock", _logger.Messages);
    }

    private const string GetCover = """{"type":"player.get_cover"}""";

    [Fact]
    public async Task Get_cover_replies_cover_in_base64()
    {
        _player.Cover = new Cover(17, "image/jpeg", [1, 2, 3, 255]);
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync(GetCover + "\n");

        Assert.Equal("""{"type":"player.cover","songId":17,"mime":"image/jpeg","data":"AQID/w=="}""", await client.ReadLineAsync());
        Assert.Equal(["GetCover"], _player.Calls);
    }

    [Fact]
    public async Task Get_cover_too_large_replies_error()
    {
        _player.CoverError = new CoverTooLargeException(Cover.MaxBytes + 1);
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync(GetCover + "\n");

        Assert.Equal("""{"type":"error","request":"player.get_cover","message":"cover too large"}""", await client.ReadLineAsync());
    }

    [Fact]
    public async Task Get_cover_with_mpd_down_replies_error_and_keeps_connection()
    {
        _player.CoverError = new MpdUnavailableException("MPD down", new IOException());
        await StartAsync();
        await using var client = await Client.ConnectAsync(SocketPath);

        await client.SendAsync(GetCover + "\n");
        Assert.Equal("""{"type":"error","request":"player.get_cover","message":"MPD down"}""", await client.ReadLineAsync());

        await client.SendAsync(GetSnapshot + "\n");
        Assert.StartsWith("""{"type":"player.snapshot",""", await client.ReadLineAsync());
    }

    [Fact]
    public async Task Observer_push_keeps_display_mode()
    {
        await StartAsync();
        await using var sub = await SubscribeAsync();
        await sub.ReadLineAsync();
        await using var buttons = await Client.ConnectAsync(SocketPath);
        await PressAsync(buttons, Menu);
        await sub.ReadLineAsync();

        await PlayingAsync("b.flac", 2);

        Assert.Equal(SnapshotMessage.Serialize(Song("b.flac", 2), "clock"), await sub.ReadLineAsync());
    }

    [Fact]
    public async Task Subscriber_that_does_not_read_is_dropped_and_commands_keep_working()
    {
        await StartAsync();
        await using var slow = await SubscribeAsync();
        await slow.ReadLineAsync();

        // Líneas grandes hasta llenar el buffer del socket: la escritura se bloquea y vence a los 2 s.
        _player.Snapshot = Song("a.flac", 1) with { CurrentTrack = new Track("a.flac", new string('x', 100_000), null, null, null) };
        for (var i = 0; i < 200 && _server.SubscriberCount > 0; i++)
            await _player.ChangeAsync();

        Assert.Equal(0, _server.SubscriberCount);
        Assert.Contains(_logger.Messages, m => m.StartsWith("Subscriber dropped"));
        await using var other = await Client.ConnectAsync(SocketPath);
        await other.SendAsync(GetSnapshot + "\n");
        Assert.StartsWith("""{"type":"player.snapshot",""", await other.ReadLineAsync());
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
