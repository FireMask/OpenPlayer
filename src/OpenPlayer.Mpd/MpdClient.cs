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

    public Task<IReadOnlyList<MpdResponse>> ExecuteAsync(IReadOnlyList<string> commands, CancellationToken ct)
    {
        foreach (var command in commands)
            if (string.IsNullOrWhiteSpace(command) || command.Contains('\n') || command.Contains('\r'))
                throw new ArgumentException($"Invalid MPD command: '{command}'.", nameof(commands));

        // ponytail: un solo timeout para toda la operación (conexión + lecturas), basta para comandos cortos.
        return SessionAsync(commands, idle: false, ct);
    }

    /// <summary>
    /// <c>idle player mixer playlist options</c> en una conexión propia: vuelve cuando cambia el reproductor, el volumen, la cola o las opciones.
    /// Solo la conexión y el saludo tienen timeout; la espera dura lo que haga falta. Cancelar cierra la conexión.
    /// </summary>
    public Task IdleAsync(CancellationToken ct) => SessionAsync(["idle player mixer playlist options"], idle: true, ct);

    private async Task<IReadOnlyList<MpdResponse>> SessionAsync(IReadOnlyList<string> commands, bool idle, CancellationToken ct)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(options.ConnectTimeout);
        try
        {
            using var tcp = new TcpClient();
            await tcp.ConnectAsync(options.Host, options.Port, timeout.Token);
            await using var stream = tcp.GetStream();
            var reader = new MpdReader(stream);
            await using var writer = new StreamWriter(stream, Utf8) { NewLine = "\n" };

            var greeting = await reader.ReadLineAsync(timeout.Token);
            if (greeting is null || !greeting.StartsWith("OK MPD ", StringComparison.Ordinal))
                throw new MpdUnavailableException($"Unexpected MPD greeting: '{greeting}'.", new InvalidDataException());

            var token = idle ? ct : timeout.Token;
            var responses = new List<MpdResponse>(commands.Count);
            foreach (var command in commands)
            {
                await writer.WriteLineAsync(command.AsMemory(), token);
                await writer.FlushAsync(token);
                responses.Add(await ReadResponseAsync(reader, command, token));
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

    private static async Task<MpdResponse> ReadResponseAsync(MpdReader reader, string command, CancellationToken ct)
    {
        var pairs = new List<KeyValuePair<string, string>>();
        byte[]? binary = null;
        while (true)
        {
            var line = await reader.ReadLineAsync(ct)
                ?? throw new IOException($"MPD closed the connection during '{command}'.");
            if (line == "OK")
                return new MpdResponse(pairs, binary);
            if (line.StartsWith("ACK ", StringComparison.Ordinal))
                throw new MpdException(command, line[4..]);

            var separator = line.IndexOf(": ", StringComparison.Ordinal);
            if (separator <= 0)
                continue;
            var key = line[..separator];
            var value = line[(separator + 2)..];
            // binary: N → N bytes crudos y un \n (SPEC 19). No queda como par.
            if (key == "binary" && int.TryParse(value, out var length) && length >= 0)
                binary = await reader.ReadBinaryAsync(length, ct);
            else
                pairs.Add(KeyValuePair.Create(key, value));
        }
    }

    /// <summary>Lee líneas UTF-8 y bloques binarios del mismo stream (un StreamReader no permite mezclarlos).</summary>
    private sealed class MpdReader(Stream stream)
    {
        private readonly byte[] _buffer = new byte[8192];
        private int _start, _end;

        /// <summary>Línea sin el \n (ni \r final), o null si el stream terminó sin datos.</summary>
        public async Task<string?> ReadLineAsync(CancellationToken ct)
        {
            using var line = new MemoryStream();
            while (true)
            {
                if (_start == _end && !await FillAsync(ct))
                    return line.Length == 0 ? null : Decode(line);
                var newline = Array.IndexOf(_buffer, (byte)'\n', _start, _end - _start);
                if (newline >= 0)
                {
                    line.Write(_buffer, _start, newline - _start);
                    _start = newline + 1;
                    return Decode(line);
                }
                line.Write(_buffer, _start, _end - _start);
                _start = _end;
            }
        }

        public async Task<byte[]> ReadBinaryAsync(int length, CancellationToken ct)
        {
            var data = new byte[length];
            var read = 0;
            while (read < length)
            {
                if (_start == _end && !await FillAsync(ct))
                    throw new IOException("MPD closed the connection inside a binary response.");
                var count = Math.Min(length - read, _end - _start);
                Array.Copy(_buffer, _start, data, read, count);
                _start += count;
                read += count;
            }
            await ReadLineAsync(ct); // el \n que cierra el bloque
            return data;
        }

        private async Task<bool> FillAsync(CancellationToken ct)
        {
            _start = 0;
            _end = await stream.ReadAsync(_buffer, ct);
            return _end > 0;
        }

        private static string Decode(MemoryStream line)
        {
            var text = Utf8.GetString(line.GetBuffer(), 0, (int)line.Length);
            return text.EndsWith('\r') ? text[..^1] : text;
        }
    }
}
