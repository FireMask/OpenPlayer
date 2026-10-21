using OpenPlayer.Core.Messages;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Tests;

public class SnapshotMessageTests
{
    private static PlaybackSnapshot Snapshot(
        PlaybackState state = PlaybackState.Stopped,
        Track? track = null,
        TimeSpan? position = null,
        TimeSpan? duration = null,
        int? volume = null,
        int? queuePosition = null,
        long? queueVersion = null) =>
        new(state, track, position, duration, volume, DateTimeOffset.UnixEpoch, queuePosition, queueVersion);

    [Fact]
    public void Serializes_full_snapshot_exactly()
    {
        var track = new Track("r/pa.flac", "Paranoid Android", "Radiohead", "OK Computer", null);

        var json = SnapshotMessage.Serialize(Snapshot(PlaybackState.Playing, track,
            TimeSpan.FromSeconds(83), TimeSpan.FromSeconds(387), 35, 3, 42));

        Assert.Equal(
            """{"type":"player.snapshot","state":"playing","trackTitle":"Paranoid Android","trackArtist":"Radiohead","positionSeconds":83,"durationSeconds":387,"volume":35,"queuePosition":3,"queueVersion":42}""",
            json);
    }

    [Fact]
    public void Serializes_nulls_explicitly()
    {
        Assert.Equal(
            """{"type":"player.snapshot","state":"stopped","trackTitle":null,"trackArtist":null,"positionSeconds":null,"durationSeconds":null,"volume":null,"queuePosition":null,"queueVersion":null}""",
            SnapshotMessage.Serialize(Snapshot()));
    }

    [Fact]
    public void Truncates_seconds()
    {
        var json = SnapshotMessage.Serialize(Snapshot(
            position: TimeSpan.FromSeconds(83.999), duration: TimeSpan.FromSeconds(0.5)));

        Assert.Contains("\"positionSeconds\":83,", json);
        Assert.Contains("\"durationSeconds\":0,", json);
    }

    [Theory]
    [InlineData(PlaybackState.Playing, "playing")]
    [InlineData(PlaybackState.Paused, "paused")]
    [InlineData(PlaybackState.Stopped, "stopped")]
    public void Maps_state_names(PlaybackState state, string expected) =>
        Assert.Contains($"\"state\":\"{expected}\"", SnapshotMessage.Serialize(Snapshot(state)));

    [Fact]
    public void Keeps_accents_readable_and_escapes_quotes()
    {
        var track = new Track("a.mp3", "Canción \"uno\"", "Café Tacvba", null, null);

        var json = SnapshotMessage.Serialize(Snapshot(track: track));

        Assert.Contains("\"trackTitle\":\"Canción \\\"uno\\\"\"", json);
        Assert.Contains("\"trackArtist\":\"Café Tacvba\"", json);
    }

    [Fact]
    public void Is_a_single_line()
    {
        var track = new Track("a.mp3", "line1\nline2", null, null, null);

        Assert.DoesNotContain('\n', SnapshotMessage.Serialize(Snapshot(track: track)));
    }
}
