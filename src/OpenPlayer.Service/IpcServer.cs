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
    ILibrary library,
    IPlaylistStore playlists,
    IQueue queue,
    ILogger<IpcServer> logger) : BackgroundService
{
    // ponytail: lock global para todos los comandos; evita que dos volume_up lean el mismo volumen.
    private readonly SemaphoreSlim _commandLock = new(1, 1);

    private Socket? _listener;

    // Nombre de la lista cargada en la cola (SPEC 11): MPD no lo guarda. Solo en memoria, protegido por _commandLock.
    private string? _loadedPlaylist;

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
        var clients = new List<Task>();
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
                    await HandleLineAsync(line, stream, ct);
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
        catch (IOException)
        {
            // El cliente cerró a mitad de una escritura.
        }
        catch (Exception e)
        {
            logger.LogError(e, "IPC client failed; closing connection");
        }
    }

    private async Task HandleLineAsync(string line, NetworkStream stream, CancellationToken ct)
    {
        if (line.Length == 0)
            return;
        if (!IpcMessageParser.TryParse(line, out var message, out var error, out var request))
        {
            logger.LogWarning("Invalid IPC message: {Error}", error);
            if (request is not null)
                await WriteLineAsync(stream, ErrorMessage.Serialize(request, error!), ct);
            return;
        }

        // Biblioteca, playlists y cola (SPEC 10, 11): siempre una línea de respuesta, ok/página/lista o error.
        if (request is not null)
        {
            string reply;
            try
            {
                string? result = null;
                await LockedAsync(async () => result = await ReplyAsync(message!, request, ct), ct);
                reply = result!;
            }
            catch (Exception e) when (e is MpdException or MpdUnavailableException or ArgumentException)
            {
                logger.LogWarning("{Request} failed: {Error}", request, e.Message);
                reply = ErrorMessage.Serialize(request, e.Message);
            }
            await WriteLineAsync(stream, reply, ct);
            return;
        }

        switch (message)
        {
            case ButtonPressed pressed:
                // sequence es opcional: el web agent no la envía (SPEC 08).
                if (pressed.Sequence is { } sequence)
                    logger.LogInformation("Button {Button} (sequence {Sequence})", pressed.Button, sequence);
                else
                    logger.LogInformation("Button {Button}", pressed.Button);
                try
                {
                    await LockedAsync(() => buttons.HandleAsync(pressed.Button, ct), ct);
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
                string reply;
                try
                {
                    PlaybackSnapshot? snapshot = null;
                    await LockedAsync(async () => snapshot = await player.GetSnapshotAsync(ct), ct);
                    reply = SnapshotMessage.Serialize(snapshot!);
                }
                catch (Exception e) when (e is MpdException or MpdUnavailableException)
                {
                    logger.LogWarning("player.get_snapshot failed: {Error}", e.Message);
                    reply = ErrorMessage.Serialize("player.get_snapshot", e.Message);
                }
                await WriteLineAsync(stream, reply, ct);
                break;
        }
    }

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
                return QueuePageMessage.Serialize(await queue.GetAsync(m.Offset, ct), _loadedPlaylist);
            case QueuePlayRequested m:
                await queue.PlayAsync(m.Position, ct);
                break;
            case LibraryPlayRequested m:
                await library.PlayTrackAsync(m.Uri, ct);
                _loadedPlaylist = null;
                break;
            case PlaylistCreateRequested m:
                await playlists.CreateAsync(m.Name, ct);
                break;
            case PlaylistRenameRequested m:
                await playlists.RenameAsync(m.Name, m.NewName, ct);
                if (m.Name == _loadedPlaylist)
                    _loadedPlaylist = m.NewName;
                break;
            case PlaylistDeleteRequested m:
                await playlists.DeleteAsync(m.Name, ct);
                if (m.Name == _loadedPlaylist)
                    _loadedPlaylist = null;
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
                _loadedPlaylist = m.Name;
                break;
            default:
                throw new InvalidOperationException($"No handler for {request}");
        }
        logger.LogInformation("{Request} ok", request);
        return OkMessage.Serialize(request);
    }

    private static Task WriteLineAsync(NetworkStream stream, string line, CancellationToken ct) =>
        stream.WriteAsync(Encoding.UTF8.GetBytes(line + "\n"), ct).AsTask();

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
