using System.Net;
using System.Net.Sockets;
using System.Text;

namespace OpenPlayer.Mpd.Tests;

/// <summary>
/// MPD falso en 127.0.0.1 con puerto asignado por el SO. Registra los comandos de cada conexión
/// y responde con <see cref="Respond"/> (por defecto, solo <c>OK</c>).
/// </summary>
internal sealed class FakeMpdServer : IAsyncDisposable
{
    private readonly TcpListener _listener = new(IPAddress.Loopback, 0);
    private readonly List<List<string>> _connections = [];
    private readonly List<Task> _handlers = [];
    private readonly Task _acceptLoop;

    /// <summary>null = no enviar saludo (simula un servidor colgado).</summary>
    public string? Greeting { get; init; } = "OK MPD 0.23.5";

    /// <summary>Cuerpo de respuesta por comando, incluido el <c>OK</c>/<c>ACK</c> final.</summary>
    public Func<string, string> Respond { get; set; } = _ => "OK\n";

    /// <summary>Respuesta en bytes crudos (binary: N de SPEC 19); si no es null, reemplaza a <see cref="Respond"/>.</summary>
    public Func<string, byte[]>? RespondBytes { get; set; }

    public FakeMpdServer()
    {
        _listener.Start();
        _acceptLoop = AcceptLoopAsync();
    }

    public int Port => ((IPEndPoint)_listener.LocalEndpoint).Port;

    public MpdOptions Options(int timeoutMs = 2000) => new("127.0.0.1", Port, TimeSpan.FromMilliseconds(timeoutMs));

    /// <summary>Comandos recibidos, agrupados por conexión.</summary>
    public List<List<string>> Connections
    {
        get { lock (_connections) return [.. _connections.Select(c => c.ToList())]; }
    }

    /// <summary>Espera a que el cliente cierre todas las conexiones abiertas hasta ahora.</summary>
    public Task AllClosed()
    {
        lock (_handlers) return Task.WhenAll(_handlers).WaitAsync(TimeSpan.FromSeconds(5));
    }

    private async Task AcceptLoopAsync()
    {
        try
        {
            while (true)
            {
                var tcp = await _listener.AcceptTcpClientAsync();
                var commands = new List<string>();
                lock (_connections) _connections.Add(commands);
                lock (_handlers) _handlers.Add(HandleAsync(tcp, commands));
            }
        }
        catch (Exception e) when (e is ObjectDisposedException or SocketException)
        {
        }
    }

    private async Task HandleAsync(TcpClient tcp, List<string> commands)
    {
        using (tcp)
        {
            var stream = tcp.GetStream();
            var reader = new StreamReader(stream, Encoding.UTF8);
            var writer = new StreamWriter(stream, new UTF8Encoding(false)) { NewLine = "\n", AutoFlush = true };
            try
            {
                if (Greeting is not null)
                    await writer.WriteLineAsync(Greeting);
                while (await reader.ReadLineAsync() is { } command)
                {
                    lock (_connections) commands.Add(command);
                    if (RespondBytes is { } raw)
                        await stream.WriteAsync(raw(command));
                    else
                        await writer.WriteAsync(Respond(command));
                }
            }
            catch (IOException)
            {
                // El cliente cortó la conexión: también cuenta como cerrada.
            }
        }
    }

    public async ValueTask DisposeAsync()
    {
        _listener.Stop();
        await _acceptLoop;
    }
}
