using System.Globalization;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Mpd;

public static class MpdSnapshotParser
{
    public static PlaybackSnapshot Parse(MpdResponse status, MpdResponse currentSong, DateTimeOffset now)
    {
        var state = status.Get("state") switch
        {
            "play" => PlaybackState.Playing,
            "pause" => PlaybackState.Paused,
            _ => PlaybackState.Stopped,
        };

        var file = currentSong.Get("file");
        var track = file is null
            ? null
            : new Track(file, currentSong.Get("Title"), currentSong.Get("Artist"), currentSong.Get("Album"),
                Seconds(currentSong.Get("duration")));

        return new PlaybackSnapshot(
            state,
            track,
            Seconds(status.Get("elapsed")),
            Seconds(status.Get("duration")),
            Volume(status.Get("volume")),
            now);
    }

    private static TimeSpan? Seconds(string? value) =>
        double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out var s) && s >= 0
            ? TimeSpan.FromSeconds(s)
            : null;

    // MPD reporta -1 cuando no hay mixer.
    private static int? Volume(string? value) =>
        int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var v) && v is >= 0 and <= 100
            ? v
            : null;
}
