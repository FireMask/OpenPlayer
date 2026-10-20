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

/// <summary>Socket Unix con JSON Lines (architecture.md §7): botones y consultas de snapshot del hardware agent.</summary>
public sealed class IpcServer(
    IpcOptions options,
    IPlayer player,
    ButtonCommandHandler buttons,
    ILogger<IpcServer> logger) : BackgroundService
{
    // ponytail: lock global para todos los comandos; evita que dos volume_up lean el mismo volumen.
    private readonly SemaphoreSlim _commandLock = new(1, 1);

    private Socket? _listener;

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
        if (!IpcMessageParser.TryParse(line, out var message, out var error))
        {
            logger.LogWarning("Invalid IPC message: {Error}", error);
            return;
        }

        switch (message)
        {
            case ButtonPressed pressed:
                logger.LogInformation("Button {Button} (sequence {Sequence})", pressed.Button, pressed.Sequence);
                try
                {
                    await LockedAsync(() => buttons.HandleAsync(pressed.Button, ct), ct);
                }
                catch (Exception e) when (e is MpdException or MpdUnavailableException)
                {
                    logger.LogWarning("Button {Button} failed: {Error}", pressed.Button, e.Message);
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
                await stream.WriteAsync(Encoding.UTF8.GetBytes(reply + "\n"), ct);
                break;
        }
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
