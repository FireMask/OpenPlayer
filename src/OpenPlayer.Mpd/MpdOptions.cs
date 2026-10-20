namespace OpenPlayer.Mpd;

public sealed record MpdOptions(string Host, int Port, TimeSpan ConnectTimeout)
{
    public string Host { get; } = !string.IsNullOrWhiteSpace(Host)
        ? Host
        : throw new ArgumentException("MPD host must not be empty.", nameof(Host));

    public int Port { get; } = Port is >= 1 and <= 65535
        ? Port
        : throw new ArgumentOutOfRangeException(nameof(Port), Port, "MPD port must be 1–65535.");

    public TimeSpan ConnectTimeout { get; } = ConnectTimeout > TimeSpan.Zero
        ? ConnectTimeout
        : throw new ArgumentOutOfRangeException(nameof(ConnectTimeout), ConnectTimeout, "MPD timeout must be > 0.");
}
