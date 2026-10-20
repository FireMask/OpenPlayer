namespace OpenPlayer.Mpd;

/// <summary>MPD respondió <c>ACK</c> a un comando.</summary>
public class MpdException(string command, string message) : Exception(message)
{
    public string Command { get; } = command;
}

/// <summary>No se pudo hablar con MPD: red, timeout o saludo inválido.</summary>
public class MpdUnavailableException(string message, Exception inner) : Exception(message, inner);
