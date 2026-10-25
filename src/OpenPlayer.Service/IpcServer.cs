using System.Net.Sockets;
using System.Text;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OpenPlayer.Core.Commands;
using OpenPlayer.Core.Interfaces;
using OpenPlayer.Core.Messages;
using OpenPlayer.Core.Models;
using OpenPlayer.Mpd;

namespace OpenPlayer.Service;

/// <summary>Socket Unix con JSON Lines (architecture.md §7): botones, snapshot, seek, biblioteca, playlists y cola.</summary>
public sealed class IpcServer(
    IpcOptions options,
    IPlayer player,
    ButtonCommandHandler buttons,
    PlayerSettings settings,
    ILibrary library,
    IPlaylistStore playlists,
    IQueue queue,
    ILogger<IpcServer> logger) : BackgroundService
{
    // ponytail: lock global para todos los comandos; evita que dos volume_up lean el mismo volumen.
    private readonly SemaphoreSlim _commandLock = new(1, 1);

    private Socket? _listener;

    // Etiqueta de origen por id de MPD (SPEC 14): MPD no guarda metadatos propios por canción de la cola.
    // Solo en memoria, protegido por _commandLock; se pierde al reiniciar el Service.
    private readonly Dictionary<int, string> _sources = [];

    private const string LibrarySource = "Biblioteca";

    // Historial de ⏮ (SPEC 15): canciones escuchadas, la más reciente al final. Solo en memoria, bajo _commandLock.
    private readonly LinkedList<PlayedSong> _history = [];
    private CurrentSong? _current;
    private const int HistoryLimit = 50;
    private static readonly TimeSpan WatchRetry = TimeSpan.FromSeconds(5);

    // Conexiones suscriptas (SPEC 16). Protegida con lock(_subscribers), no con _commandLock:
    // el envío ocurre fuera del lock global para que un suscriptor lento no frene los comandos.
    private readonly List<NetworkStream> _subscribers = [];
    private static readonly TimeSpan PushTimeout = TimeSpan.FromSeconds(2);

    // Modo de la pantalla (SPEC 18, "art" en SPEC 19): lo cicla menu. Solo en memoria, bajo _commandLock; arranca en "track".
    private string _displayMode = "track";

    internal int SubscriberCount
    {
        get { lock (_subscribers) return _subscribers.Count; }
    }

    internal sealed record PlayedSong(string Uri, string? Source);

    // Played: estuvo en play o pause mientras fue la actual. Source: su etiqueta, por si _sources ya no la tiene
    // cuando el observador ve el cambio (playlist.play reetiqueta la cola dentro del mismo lock).
    private sealed record CurrentSong(int Id, string Uri, bool Played, string? Source);

    /// <summary>Copia del historial para las pruebas.</summary>
    internal IReadOnlyList<PlayedSong> History => [.. _history];

    // Bind en StartAsync, no en ExecuteAsync (que en .NET 10 corre en segundo plano):
    // un error de bind detiene el arranque del host, y al volver el socket ya escucha.
    public override Task StartAsync(CancellationToken cancellationToken)
    {
        var path = options.SocketPath;
        // Un socket viejo (tras una caída) haría fallar el bind.
        File.Delete(path);
        _listener = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
        _listener.Bind(new UnixDomainSocketEndPoint(path));
        if (!OperatingSystem.IsWindows())
            File.SetUnixFileMode(path,
                UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.GroupRead | UnixFileMode.GroupWrite);
        _listener.Listen();
        logger.LogInformation("Listening on {Path}", path);
        return base.StartAsync(cancellationToken);
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        // En paralelo con el accept: con MPD caído no retrasa a los clientes; el próximo play activa consume igual.
        var clients = new List<Task> { EnableConsumeAsync(stoppingToken), WatchAsync(stoppingToken) };
        using (_listener)
        {
            try
            {
                while (true)
                {
                    var client = await _listener!.AcceptAsync(stoppingToken);
                    clients.RemoveAll(t => t.IsCompleted);
                    clients.Add(HandleClientAsync(client, stoppingToken));
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
            }
        }
        await Task.WhenAll(clients);
        File.Delete(options.SocketPath);
    }

    private async Task HandleClientAsync(Socket client, CancellationToken ct)
    {
        await using var stream = new NetworkStream(client, ownsSocket: true);
        // Un byte extra: llenar el buffer sin '\n' significa que la línea excede el límite.
        var buffer = new byte[options.MaxMessageBytes + 1];
        var length = 0;
        try
        {
            while (true)
            {
                var read = await stream.ReadAsync(buffer.AsMemory(length), ct);
                if (read == 0)
                    return;
                length += read;

                var start = 0;
                int newline;
                while ((newline = Array.IndexOf(buffer, (byte)'\n', start, length - start)) >= 0)
                {
                    var line = Encoding.UTF8.GetString(buffer, start, newline - start).TrimEnd('\r');
                    start = newline + 1;
                    if (await HandleLineAsync(line, stream, ct))
                    {
                        // Suscripta (SPEC 16): ya no se leen pedidos; solo se espera el cierre.
                        while (await stream.ReadAsync(buffer, ct) > 0)
                        {
                        }
                        return;
                    }
                }
                Array.Copy(buffer, start, buffer, 0, length - start);
                length -= start;

                if (length == buffer.Length)
                {
                    logger.LogWarning("IPC message exceeds {Max} bytes; closing connection", options.MaxMessageBytes);
                    return;
                }
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
        }
        catch (Exception e) when (e is IOException or ObjectDisposedException)
        {
            // El cliente cerró a mitad de una escritura, o un push fallido cerró la suscripción.
        }
        catch (Exception e)
        {
            logger.LogError(e, "IPC client failed; closing connection");
        }
        finally
        {
            lock (_subscribers)
                _subscribers.Remove(stream);
        }
    }

    /// <returns>true si la conexión quedó suscripta (SPEC 16).</returns>
    private async Task<bool> HandleLineAsync(string line, NetworkStream stream, CancellationToken ct)
    {
        if (line.Length == 0)
            return false;
        if (!IpcMessageParser.TryParse(line, out var message, out var error, out var request))
        {
            logger.LogWarning("Invalid IPC message: {Error}", error);
            if (request is not null)
                await WriteLineAsync(stream, ErrorMessage.Serialize(request, error!), ct);
            return false;
        }

        // Biblioteca, playlists y cola (SPEC 10, 11): siempre una línea de respuesta, ok/página/lista o error.
        if (request is not null)
        {
            string reply;
            try
            {
                string? result = null;
                // La carátula no toca la cola ni el volumen: sin el lock global, una imagen grande no frena los botones.
                if (message is CoverRequested)
                    result = CoverMessage.Serialize(await player.GetCoverAsync(ct));
                else
                    await LockedAsync(async () => result = await ReplyAsync(message!, request, ct), ct);
                reply = result!;
            }
            catch (CoverTooLargeException e)
            {
                logger.LogWarning("{Request} failed: {Error}", request, e.Message);
                reply = ErrorMessage.Serialize(request, "cover too large");
            }
            catch (Exception e) when (e is MpdException or MpdUnavailableException or ArgumentException)
            {
                logger.LogWarning("{Request} failed: {Error}", request, e.Message);
                reply = ErrorMessage.Serialize(request, e.Message);
            }
            await WriteLineAsync(stream, reply, ct);
            return false;
        }

        switch (message)
        {
            case ButtonPressed pressed:
                // sequence es opcional: el web agent no la envía (SPEC 08).
                if (pressed.Sequence is { } sequence)
                    logger.LogInformation("Button {Button} (sequence {Sequence})", pressed.Button, sequence);
                else
                    logger.LogInformation("Button {Button}", pressed.Button);
                if (pressed.Button == ButtonName.Menu)
                {
                    await ToggleDisplayModeAsync(ct);
                    break;
                }
                try
                {
                    await LockedAsync(() => pressed.Button == ButtonName.Previous
                        ? PreviousAsync(ct)
                        : buttons.HandleAsync(pressed.Button, ct), ct);
                }
                catch (Exception e) when (e is MpdException or MpdUnavailableException)
                {
                    logger.LogWarning("Button {Button} failed: {Error}", pressed.Button, e.Message);
                }
                break;

            case SeekRequested seek:
                var seconds = (int)seek.Position.TotalSeconds;
                logger.LogInformation("Seek to {Seconds} s", seconds);
                try
                {
                    await LockedAsync(() => player.SeekAsync(seek.Position, ct), ct);
                }
                catch (Exception e) when (e is MpdException or MpdUnavailableException)
                {
                    logger.LogWarning("Seek failed: {Error}", e.Message);
                }
                break;

            case SnapshotRequested:
                string? reply = null;
                await LockedAsync(async () => reply = await SnapshotLineAsync(ct), ct);
                await WriteLineAsync(stream, reply!, ct);
                break;

            case SubscribeRequested:
                // Snapshot y registro bajo el lock: el observador copia los suscriptores dentro del lock,
                // así nunca empuja un snapshot más viejo que este ni escribe a la vez en la misma conexión.
                // Si la escritura falla, HandleClientAsync lo quita al cerrar.
                await LockedAsync(async () =>
                {
                    lock (_subscribers)
                        _subscribers.Add(stream);
                    await WriteTimedAsync(stream, await SnapshotLineAsync(ct), ct);
                }, ct);
                logger.LogInformation("player.subscribe");
                return true;
        }
        return false;
    }

    // player.snapshot, o la línea de error si MPD falla. Se llama dentro del lock.
    private async Task<string> SnapshotLineAsync(CancellationToken ct)
    {
        try
        {
            return SnapshotMessage.Serialize(await player.GetSnapshotAsync(ct), _displayMode);
        }
        catch (Exception e) when (e is MpdException or MpdUnavailableException)
        {
            logger.LogWarning("player.get_snapshot failed: {Error}", e.Message);
            return ErrorMessage.Serialize("player.get_snapshot", e.Message);
        }
    }

    // menu no toca MPD: el observador no despertaría, así que el snapshot con el modo nuevo se empuja desde acá.
    private async Task ToggleDisplayModeAsync(CancellationToken ct)
    {
        string? line = null, mode = null;
        List<NetworkStream> targets = [];
        await LockedAsync(async () =>
        {
            mode = _displayMode = _displayMode switch { "track" => "clock", "clock" => "art", _ => "track" };
            line = await SnapshotLineAsync(ct);
            targets = Subscribers();
        }, ct);
        logger.LogInformation("Display mode {Mode}", mode);
        await PushAsync(targets, line!, ct);
    }

    private static async Task WriteTimedAsync(NetworkStream stream, string line, CancellationToken ct)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(PushTimeout);
        await WriteLineAsync(stream, line, timeout.Token);
    }

    private List<NetworkStream> Subscribers()
    {
        lock (_subscribers)
            return [.. _subscribers];
    }

    // En paralelo: un suscriptor lento no demora a los demás. Falla o timeout → se quita y se cierra.
    private Task PushAsync(List<NetworkStream> targets, string line, CancellationToken ct) =>
        Task.WhenAll(targets.Select(async stream =>
        {
            try
            {
                await WriteTimedAsync(stream, line, ct);
            }
            catch (Exception e) when (e is IOException or ObjectDisposedException
                                          || (e is OperationCanceledException && !ct.IsCancellationRequested))
            {
                logger.LogWarning("Subscriber dropped: {Error}", e.Message);
                lock (_subscribers)
                    _subscribers.Remove(stream);
                stream.Dispose();
            }
        }));

    private async Task<string> ReplyAsync(IpcMessage message, string request, CancellationToken ct)
    {
        switch (message)
        {
            case LibraryBrowseRequested m:
                return LibraryPageMessage.Serialize(await library.BrowseAsync(m.Path, m.Offset, ct));
            case LibrarySearchRequested m:
                return LibraryPageMessage.Serialize(await library.SearchAsync(m.Query, m.Offset, ct));
            case PlaylistListRequested:
                return PlaylistListMessage.Serialize(await playlists.ListAsync(ct));
            case PlaylistGetRequested m:
                return LibraryPageMessage.Serialize(await playlists.GetAsync(m.Name, m.Offset, ct));
            case QueueGetRequested m:
                // Se loguea (a diferencia de las otras consultas) para verificar que la web no sondea la cola.
                var page = await queue.GetAsync(m.Offset, ct);
                logger.LogInformation("{Request} ok (offset {Offset})", request, m.Offset);
                return QueuePageMessage.Serialize(page, _sources);
            case QueuePlayRequested m:
                await queue.PlayAsync(m.Position, ct);
                break;
            case QueueRemoveRequested m:
                await queue.RemoveAsync(m.Id, ct);
                break;
            case QueueMoveRequested m:
                await queue.MoveAsync(m.Id, m.To, ct);
                break;
            case QueueClearRequested:
                await queue.ClearAsync(ct);
                _sources.Clear();
                break;
            case QueueAddRequested m:
                var before = await TryIdsAsync(ct);
                await queue.AddAsync(m.Uri, m.Next, ct);
                var after = await TryIdsAsync(ct);
                if (after is not null)
                {
                    foreach (var id in _sources.Keys.Except(after).ToList())
                        _sources.Remove(id);  // consumidas o quitadas fuera de la web
                    if (before is not null)
                        foreach (var id in after.Except(before))
                            _sources[id] = LibrarySource;
                }
                break;
            case QueueSaveRequested m:
                await queue.SaveAsync(m.Name, ct);
                break;
            case LibraryPlayRequested m:
                await library.PlayTrackAsync(m.Uri, ct);
                await LabelQueueAsync(LibrarySource, ct);
                break;
            case PlaylistCreateRequested m:
                await playlists.CreateAsync(m.Name, ct);
                break;
            case PlaylistRenameRequested m:
                await playlists.RenameAsync(m.Name, m.NewName, ct);
                break;
            case PlaylistDeleteRequested m:
                await playlists.DeleteAsync(m.Name, ct);
                break;
            case PlaylistAddRequested m:
                await playlists.AddAsync(m.Name, m.Uri, ct);
                break;
            case PlaylistRemoveRequested m:
                await playlists.RemoveAsync(m.Name, m.Position, ct);
                break;
            case PlaylistMoveRequested m:
                await playlists.MoveAsync(m.Name, m.From, m.To, ct);
                break;
            case PlaylistPlayRequested m:
                await playlists.PlayAsync(m.Name, m.Position, ct);
                await LabelQueueAsync(m.Name, ct);
                break;
            default:
                throw new InvalidOperationException($"No handler for {request}");
        }
        logger.LogInformation("{Request} ok", request);
        return OkMessage.Serialize(request);
    }

    private static Task WriteLineAsync(NetworkStream stream, string line, CancellationToken ct) =>
        stream.WriteAsync(Encoding.UTF8.GetBytes(line + "\n"), ct).AsTask();

    // La cola se acaba de reemplazar: todas sus canciones vienen de source.
    private async Task LabelQueueAsync(string source, CancellationToken ct)
    {
        _sources.Clear();
        foreach (var id in await TryIdsAsync(ct) ?? [])
            _sources[id] = source;
    }

    // La acción ya tuvo éxito: si leer los ids falla, la respuesta sigue siendo ok y las canciones quedan sin etiqueta.
    private async Task<IReadOnlyList<int>?> TryIdsAsync(CancellationToken ct)
    {
        try
        {
            return await queue.IdsAsync(ct);
        }
        catch (Exception e) when (e is MpdException or MpdUnavailableException)
        {
            logger.LogWarning("queue ids failed: {Error}", e.Message);
            return null;
        }
    }

    private async Task EnableConsumeAsync(CancellationToken ct)
    {
        try
        {
            await LockedAsync(() => queue.EnableConsumeAsync(ct), ct);
            logger.LogInformation("consume on");
        }
        catch (Exception e) when (e is MpdException or MpdUnavailableException)
        {
            logger.LogWarning("consume failed: {Error}", e.Message);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
        }
    }

    // ⏮ con historial (SPEC 15): hasta el umbral (o sin posición) vuelve a la última escuchada, arriba de la cola.
    // Si no hay historial, pasó el umbral o el archivo ya no existe: ButtonCommandHandler, que reinicia la actual.
    private async Task PreviousAsync(CancellationToken ct)
    {
        if (_history.Last?.Value is { } last
            && !((await player.GetSnapshotAsync(ct)).Position > settings.PreviousRestartThreshold))
        {
            _history.RemoveLast();
            try
            {
                await queue.RestoreAsync(last.Uri, ct);
                if (last.Source is { } source && await TryIdsAsync(ct) is [var id, ..])
                    _sources[id] = source;
                // Sin actual, el observador no manda al historial la que sonaba: así ⏮⏮ no rebota.
                _current = null;
                return;
            }
            catch (MpdException e)
            {
                logger.LogWarning("restore {Uri} failed: {Error}", last.Uri, e.Message);
            }
        }
        await buttons.HandleAsync(ButtonName.Previous, ct);
    }

    // Observador (SPEC 15): snapshot, idle, snapshot... Un cambio entre el snapshot y el idle se ve al despertar.
    // Cada snapshot (o error de MPD) se empuja a los suscriptores (SPEC 16), fuera del lock.
    private async Task WatchAsync(CancellationToken ct)
    {
        try
        {
            while (true)
            {
                try
                {
                    string? line = null;
                    List<NetworkStream> targets = [];
                    await LockedAsync(async () =>
                    {
                        var snapshot = await player.GetSnapshotAsync(ct);
                        Observe(snapshot);
                        line = SnapshotMessage.Serialize(snapshot, _displayMode);
                        targets = Subscribers();
                    }, ct);
                    await PushAsync(targets, line!, ct);
                    await player.WaitForChangeAsync(ct);
                }
                catch (Exception e) when (e is MpdException or MpdUnavailableException)
                {
                    logger.LogWarning("player watch failed: {Error}", e.Message);
                    await PushAsync(Subscribers(), ErrorMessage.Serialize("player.get_snapshot", e.Message), ct);
                    await Task.Delay(WatchRetry, ct);
                }
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
        }
    }

    // Cambió la canción: la anterior entra al historial si llegó a sonar.
    private void Observe(PlaybackSnapshot snapshot)
    {
        var id = snapshot.CurrentTrack is null ? null : snapshot.SongId;
        if (_current is { } old && old.Id != id && old.Played)
        {
            _history.AddLast(new PlayedSong(old.Uri, _sources.GetValueOrDefault(old.Id) ?? old.Source));
            if (_history.Count > HistoryLimit)
                _history.RemoveFirst();
        }
        var same = _current?.Id == id ? _current : null;
        _current = id is int songId
            ? new CurrentSong(songId, snapshot.CurrentTrack!.Uri,
                same?.Played == true || snapshot.State != PlaybackState.Stopped,
                _sources.GetValueOrDefault(songId) ?? same?.Source)
            : null;
    }

    private async Task LockedAsync(Func<Task> action, CancellationToken ct)
    {
        await _commandLock.WaitAsync(ct);
        try
        {
            await action();
        }
        finally
        {
            _commandLock.Release();
        }
    }
}
