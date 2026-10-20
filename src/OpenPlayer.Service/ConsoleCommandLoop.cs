using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OpenPlayer.Core.Commands;
using OpenPlayer.Core.Interfaces;
using OpenPlayer.Core.Messages;
using OpenPlayer.Mpd;

namespace OpenPlayer.Service;

/// <summary>Lee comandos por stdin: nombres de botón IPC, <c>status</c> y <c>quit</c>.</summary>
public sealed class ConsoleCommandLoop(
    IPlayer player,
    ButtonCommandHandler buttons,
    IHostApplicationLifetime lifetime,
    ILogger<ConsoleCommandLoop> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        logger.LogInformation("Ready. Commands: play_pause, previous, next, volume_up, volume_down, menu, status, quit");
        try
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                // Console.In no se puede cancelar: el hilo de lectura queda huérfano al salir, sin bloquear Ctrl+C.
                var line = await Task.Run(Console.In.ReadLine, CancellationToken.None).WaitAsync(stoppingToken);
                if (line is null)
                    break;
                // Trim no quita el BOM que algunos shells (PowerShell 5.1) anteponen al hacer pipe.
                var command = line.Trim().TrimStart('﻿');
                if (command == "quit")
                    break;
                await HandleAsync(command, stoppingToken);
            }
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
        }
        lifetime.StopApplication();
    }

    private async Task HandleAsync(string command, CancellationToken ct)
    {
        if (command.Length == 0)
            return;
        try
        {
            if (command == "status")
                Console.Out.WriteLine(SnapshotMessage.Serialize(await player.GetSnapshotAsync(ct)));
            else if (ButtonNames.TryParse(command, out var button))
            {
                await buttons.HandleAsync(button, ct);
                logger.LogInformation("{Command} ok", command);
            }
            else
                logger.LogWarning("Unknown command '{Command}'", command);
        }
        catch (Exception e) when (e is MpdException or MpdUnavailableException)
        {
            logger.LogWarning("{Command} failed: {Error}", command, e.Message);
        }
    }
}
