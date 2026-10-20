using OpenPlayer.Core.Models;
using OpenPlayer.Mpd;

namespace OpenPlayer.Service;

/// <summary>Secciones de player.json que usa el Service. "hardware" se ignora (lo lee el agente).</summary>
public sealed class PlayerConfig
{
    public MpdSection Mpd { get; set; } = new();
    public PlayerSection Player { get; set; } = new();
    public IpcSection Ipc { get; set; } = new();

    public sealed class MpdSection
    {
        public string Host { get; set; } = "";
        public int Port { get; set; }
        public int ConnectTimeoutMs { get; set; }

        public MpdOptions ToOptions() => new(Host, Port, TimeSpan.FromMilliseconds(ConnectTimeoutMs));
    }

    public sealed class PlayerSection
    {
        public int InitialVolume { get; set; }
        public int VolumeStep { get; set; }
        public double PreviousRestartThresholdSeconds { get; set; }

        public PlayerSettings ToSettings() =>
            new(VolumeStep, InitialVolume, TimeSpan.FromSeconds(PreviousRestartThresholdSeconds));
    }

    public sealed class IpcSection
    {
        public string UnixSocketPath { get; set; } = "";
        public int MaxMessageBytes { get; set; }

        public IpcOptions ToOptions() => new(UnixSocketPath, MaxMessageBytes);
    }
}

public sealed record IpcOptions(string SocketPath, int MaxMessageBytes)
{
    public string SocketPath { get; } = !string.IsNullOrWhiteSpace(SocketPath)
        ? SocketPath
        : throw new ArgumentException("ipc.unixSocketPath must not be empty.", nameof(SocketPath));

    public int MaxMessageBytes { get; } = MaxMessageBytes is >= 256 and <= 65536
        ? MaxMessageBytes
        : throw new ArgumentOutOfRangeException(nameof(MaxMessageBytes), MaxMessageBytes, "ipc.maxMessageBytes must be 256–65536.");
}
