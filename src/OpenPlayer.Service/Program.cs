using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OpenPlayer.Core.Commands;
using OpenPlayer.Core.Interfaces;
using OpenPlayer.Core.Models;
using OpenPlayer.Mpd;
using OpenPlayer.Service;

var configPath = Path.Combine(AppContext.BaseDirectory, "player.json");
if (!File.Exists(configPath))
{
    Console.Error.WriteLine($"Config file not found: {configPath}");
    return 1;
}

var builder = Host.CreateApplicationBuilder(args);
builder.Configuration.AddJsonFile(configPath, optional: false);

MpdOptions mpdOptions;
PlayerSettings playerSettings;
IpcOptions ipcOptions;
try
{
    var config = builder.Configuration.Get<PlayerConfig>() ?? new PlayerConfig();
    mpdOptions = config.Mpd.ToOptions();
    playerSettings = config.Player.ToSettings();
    ipcOptions = config.Ipc.ToOptions();
}
catch (Exception e) when (e is ArgumentException or InvalidOperationException or FormatException)
{
    Console.Error.WriteLine($"Invalid config in {configPath}: {e.Message}");
    return 1;
}

// /run/openplayer lo crea systemd (RuntimeDirectory); el Service no lo crea.
var socketDir = Path.GetDirectoryName(Path.GetFullPath(ipcOptions.SocketPath));
if (!Directory.Exists(socketDir))
{
    Console.Error.WriteLine($"Invalid config in {configPath}: ipc.unixSocketPath directory not found: {socketDir}");
    return 1;
}

// Logs de una línea a stderr (journald los captura bajo systemd).
builder.Logging.ClearProviders();
builder.Logging.AddSimpleConsole(o => o.SingleLine = true);
builder.Logging.Services.Configure<Microsoft.Extensions.Logging.Console.ConsoleLoggerOptions>(
    o => o.LogToStandardErrorThreshold = LogLevel.Trace);
builder.Services.Configure<ConsoleLifetimeOptions>(o => o.SuppressStatusMessages = true);

builder.Services.AddSingleton(mpdOptions);
builder.Services.AddSingleton(playerSettings);
builder.Services.AddSingleton(ipcOptions);
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddSingleton<MpdClient>();
builder.Services.AddSingleton<IPlayer, MpdPlayer>();
builder.Services.AddSingleton<ButtonCommandHandler>();
builder.Services.AddHostedService<IpcServer>();

try
{
    await builder.Build().RunAsync();
}
catch (Exception e)
{
    // El host ya registró el detalle (p. ej. bind del socket fallido); exit 1 para que systemd lo vea como fallo.
    Console.Error.WriteLine($"Service failed: {e.Message}");
    return 1;
}
return 0;
