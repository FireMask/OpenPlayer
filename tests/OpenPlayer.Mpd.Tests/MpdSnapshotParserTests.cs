using System.Globalization;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Mpd.Tests;

public class MpdSnapshotParserTests
{
    private static readonly DateTimeOffset Now = new(2026, 10, 20, 12, 0, 0, TimeSpan.Zero);

    private static MpdResponse Resp(params string[] lines) =>
        new([.. lines.Select(l => l.Split(": ", 2)).Select(p => KeyValuePair.Create(p[0], p[1]))]);

    [Fact]
    public void Parses_full_playing_snapshot()
    {
        var status = Resp("volume: 35", "state: play", "elapsed: 83.512", "duration: 387.240");
        var song = Resp("file: Radiohead/OK Computer/02.flac", "Title: Paranoid Android", "Artist: Radiohead",
            "Album: OK Computer", "duration: 387.240");

        var s = MpdSnapshotParser.Parse(status, song, Now);

        Assert.Equal(PlaybackState.Playing, s.State);
        Assert.Equal(TimeSpan.FromSeconds(83.512), s.Position);
        Assert.Equal(TimeSpan.FromSeconds(387.24), s.Duration);
        Assert.Equal(35, s.Volume);
        Assert.Equal(Now, s.UpdatedAt);
        Assert.Equal(new Track("Radiohead/OK Computer/02.flac", "Paranoid Android", "Radiohead", "OK Computer",
            TimeSpan.FromSeconds(387.24)), s.CurrentTrack);
    }

    [Theory]
    [InlineData("play", PlaybackState.Playing)]
    [InlineData("pause", PlaybackState.Paused)]
    [InlineData("stop", PlaybackState.Stopped)]
    [InlineData("weird", PlaybackState.Stopped)]
    public void Maps_state(string mpdState, PlaybackState expected) =>
        Assert.Equal(expected, MpdSnapshotParser.Parse(Resp($"state: {mpdState}"), Resp(), Now).State);

    [Fact]
    public void Missing_state_is_stopped() =>
        Assert.Equal(PlaybackState.Stopped, MpdSnapshotParser.Parse(Resp(), Resp(), Now).State);

    [Fact]
    public void Volume_minus_one_is_null() =>
        Assert.Null(MpdSnapshotParser.Parse(Resp("volume: -1", "state: stop"), Resp(), Now).Volume);

    [Fact]
    public void Missing_fields_are_null()
    {
        var s = MpdSnapshotParser.Parse(Resp("state: stop"), Resp(), Now);

        Assert.Null(s.Position);
        Assert.Null(s.Duration);
        Assert.Null(s.Volume);
        Assert.Null(s.CurrentTrack);
        Assert.Null(s.QueuePosition);
        Assert.Null(s.QueueVersion);
    }

    [Fact]
    public void Parses_queue_position_and_version()
    {
        var s = MpdSnapshotParser.Parse(Resp("state: play", "song: 3", "playlist: 42"), Resp(), Now);

        Assert.Equal(3, s.QueuePosition);
        Assert.Equal(42L, s.QueueVersion);
    }

    [Theory]
    [InlineData("x")]
    [InlineData("-1")]
    [InlineData("1.5")]
    [InlineData("")]
    public void Non_numeric_queue_fields_are_null(string value)
    {
        var s = MpdSnapshotParser.Parse(Resp("state: play", $"song: {value}", $"playlist: {value}"), Resp(), Now);

        Assert.Null(s.QueuePosition);
        Assert.Null(s.QueueVersion);
    }

    [Fact]
    public void Song_without_file_has_no_track() =>
        Assert.Null(MpdSnapshotParser.Parse(Resp("state: play"), Resp("Title: Orphan"), Now).CurrentTrack);

    [Fact]
    public void Song_without_tags_has_null_tags()
    {
        var track = MpdSnapshotParser.Parse(Resp("state: play"), Resp("file: a.mp3"), Now).CurrentTrack;

        Assert.Equal(new Track("a.mp3", null, null, null, null), track);
    }

    [Fact]
    public void Decimals_ignore_current_culture()
    {
        var previous = CultureInfo.CurrentCulture;
        CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("es-ES"); // coma decimal
        try
        {
            var s = MpdSnapshotParser.Parse(Resp("state: play", "elapsed: 1.5"), Resp(), Now);
            Assert.Equal(TimeSpan.FromSeconds(1.5), s.Position);
        }
        finally
        {
            CultureInfo.CurrentCulture = previous;
        }
    }

    [Fact]
    public void Get_returns_first_value()
    {
        Assert.Equal("1", Resp("k: 1", "k: 2").Get("k"));
        Assert.Null(Resp("k: 1").Get("K"));
    }
}
