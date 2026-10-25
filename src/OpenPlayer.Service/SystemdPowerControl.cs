using System.Diagnostics;
using OpenPlayer.Core.Interfaces;

namespace OpenPlayer.Service;

/// <summary><c>systemctl poweroff</c> vía logind; el permiso lo da la regla polkit (deploy/50-openplayer-poweroff.rules).</summary>
public sealed class SystemdPowerControl : IPowerControl
{
    private static readonly TimeSpan Timeout = TimeSpan.FromSeconds(5);

    public async Task PowerOffAsync(CancellationToken ct = default)
    {
        using var process = Process.Start(new ProcessStartInfo("systemctl", "poweroff")
        {
            RedirectStandardError = true,
            UseShellExecute = false,
        })!;
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(Timeout);
        string error;
        try
        {
            error = await process.StandardError.ReadToEndAsync(timeout.Token);
            await process.WaitForExitAsync(timeout.Token);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            process.Kill();
            throw new TimeoutException($"systemctl poweroff did not finish in {Timeout.TotalSeconds} s");
        }
        if (process.ExitCode != 0)
            throw new InvalidOperationException($"systemctl poweroff exited {process.ExitCode}: {error.Trim()}");
    }
}
