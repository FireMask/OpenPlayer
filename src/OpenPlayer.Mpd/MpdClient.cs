using System.Net.Sockets;
using System.Text;

namespace OpenPlayer.Mpd;

/// <summary>Una conexión TCP por llamada: saludo, comandos en orden, cierre.</summary>
public sealed class MpdClient(MpdOptions options)
{
    private static readonly UTF8Encoding Utf8 = new(encoderShouldEmitUTF8Identifier: false);

    /// <summary>Argumento de texto entre comillas dobles, con <c>\</c> y <c>"</c> escapados.</summary>
    public static string Quote(string argument) =>
        "\"" + argument.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";

    public async Task<IReadOnlyList<MpdResponse>> ExecuteAsync(IReadOnlyList<string> commands, CancellationToken ct)
    {
        foreach (var command in commands)
            if (string.IsNullOrWhiteSpace(command) || command.Contains('\n') || command.Contains('\r'))
                throw new ArgumentException($"Invalid MPD command: '{command}'.", nameof(commands));

        // ponytail: un solo timeout para toda la operación (conexión + lecturas), basta para comandos cortos.
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(options.ConnectTimeout);
        try
        {
            using var tcp = new TcpClient();
            await tcp.ConnectAsync(options.Host, options.Port, timeout.Token);
            await using var stream = tcp.GetStream();
            using var reader = new StreamReader(stream, Utf8);
            await using var writer = new StreamWriter(stream, Utf8) { NewLine = "\n" };

            var greeting = await reader.ReadLineAsync(timeout.Token);
            if (greeting is null || !greeting.StartsWith("OK MPD ", StringComparison.Ordinal))
                throw new MpdUnavailableException($"Unexpected MPD greeting: '{greeting}'.", new InvalidDataException());

            var responses = new List<MpdResponse>(commands.Count);
            foreach (var command in commands)
            {
                await writer.WriteLineAsync(command.AsMemory(), timeout.Token);
                await writer.FlushAsync(timeout.Token);
                responses.Add(await ReadResponseAsync(reader, command, timeout.Token));
            }
            return responses;
        }
        catch (OperationCanceledException e) when (!ct.IsCancellationRequested)
        {
            throw new MpdUnavailableException(
                $"MPD at {options.Host}:{options.Port} did not respond within {options.ConnectTimeout.TotalMilliseconds} ms.", e);
        }
        catch (Exception e) when (e is SocketException or IOException)
        {
            throw new MpdUnavailableException($"Cannot talk to MPD at {options.Host}:{options.Port}: {e.Message}", e);
        }
    }

    private static async Task<MpdResponse> ReadResponseAsync(StreamReader reader, string command, CancellationToken ct)
    {
        var pairs = new List<KeyValuePair<string, string>>();
        while (true)
        {
            var line = await reader.ReadLineAsync(ct)
                ?? throw new IOException($"MPD closed the connection during '{command}'.");
            if (line == "OK")
                return new MpdResponse(pairs);
            if (line.StartsWith("ACK ", StringComparison.Ordinal))
                throw new MpdException(command, line[4..]);

            var separator = line.IndexOf(": ", StringComparison.Ordinal);
            if (separator > 0)
                pairs.Add(KeyValuePair.Create(line[..separator], line[(separator + 2)..]));
        }
    }
}
