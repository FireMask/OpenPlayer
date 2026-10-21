using OpenPlayer.Core.Interfaces;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Commands;

public sealed class ButtonCommandHandler(IPlayer player, PlayerSettings settings)
{
    private readonly IPlayer _player = player ?? throw new ArgumentNullException(nameof(player));
    private readonly PlayerSettings _settings = settings ?? throw new ArgumentNullException(nameof(settings));

    public Task HandleAsync(ButtonName button, CancellationToken ct = default) => button switch
    {
        ButtonName.PlayPause => _player.TogglePlaybackAsync(ct),
        ButtonName.Next => _player.NextAsync(ct),
        ButtonName.Previous => PreviousAsync(ct),
        ButtonName.VolumeUp => ChangeVolumeAsync(_settings.VolumeStep, ct),
        ButtonName.VolumeDown => ChangeVolumeAsync(-_settings.VolumeStep, ct),
        ButtonName.Menu => Task.CompletedTask,
        ButtonName.RefreshLibrary => _player.UpdateLibraryAsync(ct),
        _ => throw new ArgumentOutOfRangeException(nameof(button), button, null),
    };

    // Recorta a 0–100. Volumen null (sin mixer) = no hacer nada.
    private async Task ChangeVolumeAsync(int delta, CancellationToken ct)
    {
        var snapshot = await _player.GetSnapshotAsync(ct);
        if (snapshot.Volume is int current)
            await _player.SetVolumeAsync(Math.Clamp(current + delta, Volume.Min, Volume.Max), ct);
    }

    // Pasado el umbral reinicia la pista; antes (o sin posición conocida) va a la anterior.
    private async Task PreviousAsync(CancellationToken ct)
    {
        var snapshot = await _player.GetSnapshotAsync(ct);
        if (snapshot.Position > _settings.PreviousRestartThreshold)
            await _player.SeekAsync(TimeSpan.Zero, ct);
        else
            await _player.PreviousAsync(ct);
    }
}
