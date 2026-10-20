using OpenPlayer.Core.Models;
using OpenPlayer.Mpd;

namespace OpenPlayer.Service;

/// <summary>Secciones de player.json que usa el Service. "ipc" y "hardware" se ignoran.</summary>
public sealed class PlayerConfig
{
    public MpdSection Mpd { get; set; } = new();
    public PlayerSection Player { get; set; } = new();

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
}
