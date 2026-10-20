# Compila OpenPlayer.Service para linux-arm64 y lo instala en ~/openplayer de la Pi.
# Uso: .\deploy.ps1 -Device mpi3-player.local -User andres [-Password ...]
# Sin -Password, ssh la pide (o usa tu clave SSH). player.json de la Pi no se sobrescribe.
param(
    [Parameter(Mandatory)][string]$Device,
    [Parameter(Mandatory)][string]$User,
    [string]$Password
)
$ErrorActionPreference = 'Stop'
$out = Join-Path $PSScriptRoot 'publish\linux-arm64'
$tgz = Join-Path $env:TEMP 'openplayer.tgz'
$target = "$User@$Device"

dotnet publish (Join-Path $PSScriptRoot 'src\OpenPlayer.Service') -c Release -r linux-arm64 --self-contained true -o $out
if ($LASTEXITCODE) { throw 'dotnet publish falló' }

# Un solo archivo comprimido: scp de 225 archivos sueltos es lento.
tar -czf $tgz -C $out .
if ($LASTEXITCODE) { throw 'tar falló' }

if ($Password) {
    # ponytail: la contraseña viaja por SSH_ASKPASS; usa ssh-copy-id y omite -Password para no exponerla.
    $askpass = Join-Path $env:TEMP 'openplayer-askpass.cmd'
    Set-Content $askpass '@echo %OPENPLAYER_PW%' -Encoding ascii
    $env:OPENPLAYER_PW = $Password
    $env:SSH_ASKPASS = $askpass
    $env:SSH_ASKPASS_REQUIRE = 'force'
}
try {
    scp -o StrictHostKeyChecking=accept-new $tgz "${target}:/tmp/openplayer.tgz"
    if ($LASTEXITCODE) { throw 'scp falló' }
    ssh $target 'set -e; d=~/openplayer; mkdir -p $d; tar -xzmf /tmp/openplayer.tgz -C $d --exclude=./player.json; [ -f $d/player.json ] || tar -xzmf /tmp/openplayer.tgz -C $d ./player.json; chmod +x $d/OpenPlayer.Service; rm /tmp/openplayer.tgz; echo "Instalado en $d"'
    if ($LASTEXITCODE) { throw 'instalación remota falló' }
}
finally {
    Remove-Item $tgz -ErrorAction SilentlyContinue
    if ($Password) {
        Remove-Item $askpass -ErrorAction SilentlyContinue
        Remove-Item Env:OPENPLAYER_PW, Env:SSH_ASKPASS, Env:SSH_ASKPASS_REQUIRE -ErrorAction SilentlyContinue
    }
}
