# Compila OpenPlayer.Service para linux-arm64 y lo instala en la Pi como unidad systemd (deploy/install.sh).
# Uso: .\deploy.ps1 -Device mpi3-player.local -User andres [-Password ...]
# -Password sirve para ssh y sudo. Sin él, ssh usa tu clave SSH (o la pide) y sudo la pide en la terminal.
# player.json de la Pi (/opt/openplayer) no se sobrescribe.
param(
    [Parameter(Mandatory)][string]$Device,
    [Parameter(Mandatory)][string]$User,
    [string]$Password
)
$ErrorActionPreference = 'Stop'
$out = Join-Path $PSScriptRoot 'publish\linux-arm64'
$tgz = Join-Path $env:TEMP 'openplayer.tgz'
$target = "$User@$Device"
$remote = '/tmp/openplayer-deploy'

dotnet publish (Join-Path $PSScriptRoot 'src\OpenPlayer.Service') -c Release -r linux-arm64 --self-contained true -o $out
if ($LASTEXITCODE) { throw 'dotnet publish falló' }

# Un solo archivo comprimido: scp de 225 archivos sueltos es lento. Incluye el hardware agent (solo .py).
tar -czf $tgz --exclude=__pycache__ --exclude=requirements-dev.txt -C $out . -C (Join-Path $PSScriptRoot 'src') hardware-agent
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
    ssh -o StrictHostKeyChecking=accept-new $target "mkdir -p $remote"
    if ($LASTEXITCODE) { throw 'ssh falló' }
    $deploy = Join-Path $PSScriptRoot 'deploy'
    scp $tgz "$deploy\install.sh" "$deploy\openplayer.service" "$deploy\openplayer-hardware.service" "${target}:$remote/"
    if ($LASTEXITCODE) { throw 'scp falló' }

    $install = "bash $remote/install.sh $remote/openplayer.tgz $remote/openplayer.service $User"
    $cleanup = "rc=`$?; rm -r $remote; exit `$rc"
    if ($Password) {
        # La contraseña va por stdin a sudo -S, no en la línea de comandos. El pipe de PowerShell 5.1 puede
        # anteponer un BOM UTF-8 y añade \r\n; sed quita ambos para que sudo reciba la contraseña limpia.
        $Password | ssh $target "sed -e '1s/^\xEF\xBB\xBF//' -e 's/\r$//' | sudo -S -p '' $install; $cleanup"
    }
    else {
        ssh -t $target "sudo $install; $cleanup"
    }
    if ($LASTEXITCODE) { throw 'instalación remota falló' }
}
finally {
    Remove-Item $tgz -ErrorAction SilentlyContinue
    if ($Password) {
        Remove-Item $askpass -ErrorAction SilentlyContinue
        Remove-Item Env:OPENPLAYER_PW, Env:SSH_ASKPASS, Env:SSH_ASKPASS_REQUIRE -ErrorAction SilentlyContinue
    }
}
