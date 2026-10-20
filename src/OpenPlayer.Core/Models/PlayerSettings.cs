namespace OpenPlayer.Core.Models;

public sealed record PlayerSettings
{
    public static readonly TimeSpan DefaultPreviousRestartThreshold = TimeSpan.FromSeconds(3);

    public int VolumeStep { get; }
    public int InitialVolume { get; }
    public TimeSpan PreviousRestartThreshold { get; }

    public PlayerSettings(int volumeStep = 5, int initialVolume = 35, TimeSpan? previousRestartThreshold = null)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(volumeStep, 1);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(volumeStep, Volume.Max);
        var threshold = previousRestartThreshold ?? DefaultPreviousRestartThreshold;
        ArgumentOutOfRangeException.ThrowIfLessThan(threshold, TimeSpan.Zero);

        VolumeStep = volumeStep;
        InitialVolume = Volume.EnsureValid(initialVolume);
        PreviousRestartThreshold = threshold;
    }
}
