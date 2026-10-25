namespace OpenPlayer.Mpd;

/// <summary>Pares <c>clave: valor</c> de una respuesta MPD, en el orden recibido.</summary>
/// <param name="binary">Bytes de la sección <c>binary: N</c> (SPEC 19: readpicture/albumart), o null si no vino.</param>
public sealed class MpdResponse(IReadOnlyList<KeyValuePair<string, string>> pairs, byte[]? binary = null)
{
    public IReadOnlyList<KeyValuePair<string, string>> Pairs { get; } = pairs;

    public byte[]? Binary { get; } = binary;

    public string? Get(string key)
    {
        foreach (var pair in Pairs)
            if (pair.Key == key)
                return pair.Value;
        return null;
    }
}
