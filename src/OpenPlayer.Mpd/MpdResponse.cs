namespace OpenPlayer.Mpd;

/// <summary>Pares <c>clave: valor</c> de una respuesta MPD, en el orden recibido.</summary>
public sealed class MpdResponse(IReadOnlyList<KeyValuePair<string, string>> pairs)
{
    public IReadOnlyList<KeyValuePair<string, string>> Pairs { get; } = pairs;

    public string? Get(string key)
    {
        foreach (var pair in Pairs)
            if (pair.Key == key)
                return pair.Value;
        return null;
    }
}
