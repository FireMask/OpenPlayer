namespace OpenPlayer.Core.Interfaces;

public interface IPowerControl
{
    /// <summary>Apaga el sistema. Lanza si no se pudo pedir el apagado.</summary>
    Task PowerOffAsync(CancellationToken ct = default);
}
