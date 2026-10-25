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
        // Los maneja IpcServer: modo de pantalla y apagado no tocan MPD.
        ButtonName.Menu or ButtonName.PowerOff => Task.CompletedTask,
        ButtonName.RefreshLibrary => _player.UpdateLibraryAsync(ct),
        ButtonName.SeekForward => SeekRelativeAsync(_settings.SeekStepSeconds, ct),
        ButtonName.SeekBackward => SeekRelativeAsync(-_settings.SeekStepSeconds, ct),
        _ => throw new ArgumentOutOfRangeException(nameof(button), button, null),
    };

    // Recorta a 0–100. Volumen null (sin mixer) = no hacer nada.
    private async Task ChangeVolumeAsync(int delta, CancellationToken ct)
    {
        var snapshot = await _player.GetSnapshotAsync(ct);
        if (snapshot.Volume is int current)
            await _player.SetVolumeAsync(Math.Clamp(current + delta, Volume.Min, Volume.Max), ct);
    }

    // Recorta a [0, duración − 1 s] para no cambiar de pista. Sin posición o detenido = no hacer nada.
    private async Task SeekRelativeAsync(int deltaSeconds, CancellationToken ct)
    {
        var snapshot = await _player.GetSnapshotAsync(ct);
        if (snapshot.State == PlaybackState.Stopped || snapshot.Position is not TimeSpan position)
            return;
        var target = position + TimeSpan.FromSeconds(deltaSeconds);
        if (snapshot.Duration is TimeSpan duration)
            target = TimeSpan.FromTicks(Math.Min(target.Ticks, (duration - TimeSpan.FromSeconds(1)).Ticks));
        await _player.SeekAsync(target < TimeSpan.Zero ? TimeSpan.Zero : target, ct);
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
