namespace OpenPlayer.Core.Commands;

public enum ButtonName { PlayPause, Previous, Next, VolumeUp, VolumeDown, Menu, RefreshLibrary }

public static class ButtonNames
{
    /// <summary>Parsea los nombres del contrato IPC (gpio-map.md §5). Exacto y sensible a mayúsculas.</summary>
    public static bool TryParse(string? value, out ButtonName button)
    {
        ButtonName? parsed = value switch
        {
            "play_pause" => ButtonName.PlayPause,
            "previous" => ButtonName.Previous,
            "next" => ButtonName.Next,
            "volume_up" => ButtonName.VolumeUp,
            "volume_down" => ButtonName.VolumeDown,
            "menu" => ButtonName.Menu,
            "refresh_library" => ButtonName.RefreshLibrary,
            _ => null,
        };
        button = parsed.GetValueOrDefault();
        return parsed.HasValue;
    }
}
