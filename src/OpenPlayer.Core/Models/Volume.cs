namespace OpenPlayer.Core.Models;

public static class Volume
{
    public const int Min = 0;
    public const int Max = 100;

    public static int EnsureValid(int volume)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(volume, Min);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(volume, Max);
        return volume;
    }
}
