# Fabrication output for JLCPCB: Gerbers + drill (zipped), BOM CSV and top/bottom renders.
# Usage: .\hardware\common\export-fab.ps1 -Board pcb|buttons [-KiCadCli "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"]
# -Board is a folder under hardware/ holding one .kicad_pro; file names follow that project.
# Refuses to export if ERC or DRC (with schematic parity) report anything.
param(
    [Parameter(Mandatory)][string]$Board,
    [string]$KiCadCli = 'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe'
)
$ErrorActionPreference = 'Stop'
$boardDir = Join-Path (Split-Path $PSScriptRoot) $Board
$pro = @(Get-ChildItem $boardDir -Filter '*.kicad_pro')
if ($pro.Count -ne 1) { throw "expected one .kicad_pro in $boardDir, found $($pro.Count)" }
$name = $pro[0].BaseName
$sch = Join-Path $boardDir "$name.kicad_sch"
$pcb = Join-Path $boardDir "$name.kicad_pcb"
$fab = Join-Path $boardDir 'fabrication'
$gerbers = Join-Path $fab 'gerbers'

function Invoke-KiCad([string]$what) {
    & $KiCadCli @args | Out-Null  # reports land in fabrication/; failures surface through the exit code
    if ($LASTEXITCODE) { throw "$what failed (exit $LASTEXITCODE)" }
}

Remove-Item $fab -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $gerbers | Out-Null

Invoke-KiCad 'ERC' sch erc --exit-code-violations -o (Join-Path $fab 'erc.rpt') $sch
Invoke-KiCad 'DRC' pcb drc --schematic-parity --exit-code-violations -o (Join-Path $fab 'drc.rpt') $pcb

$layers = 'F.Cu,B.Cu,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts'
Invoke-KiCad 'Gerber export' pcb export gerbers --layers $layers -o $gerbers $pcb
Invoke-KiCad 'Drill export' pcb export drill --format excellon --excellon-units mm -o "$gerbers\" $pcb
Compress-Archive -Path (Join-Path $gerbers '*') -DestinationPath (Join-Path $fab "$name-gerbers.zip")

Invoke-KiCad 'BOM export' sch export bom -o (Join-Path $fab "$name-bom.csv") `
    --fields 'Reference,Value,Footprint,${QUANTITY}' --labels 'Refs,Value,Footprint,Qty' --group-by 'Value,Footprint' $sch

Invoke-KiCad 'Top render' pcb render --side top --quality high --background opaque --width 1600 --height 1200 -o (Join-Path $fab 'render-top.png') $pcb
Invoke-KiCad 'Bottom render' pcb render --side bottom --quality high --background opaque --width 1600 --height 1200 -o (Join-Path $fab 'render-bottom.png') $pcb

Write-Host "Fabrication files in $fab"
