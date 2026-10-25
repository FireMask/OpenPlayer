using OpenPlayer.Core.Interfaces;

namespace OpenPlayer.Service.Tests;

/// <summary>Cuenta los apagados pedidos, o lanza <see cref="Error"/>.</summary>
internal sealed class FakePowerControl : IPowerControl
{
    public int Calls { get; private set; }

    public Exception? Error { get; set; }

    public Task PowerOffAsync(CancellationToken ct = default)
    {
        Calls++;
        return Error is { } e ? Task.FromException(e) : Task.CompletedTask;
    }
}
