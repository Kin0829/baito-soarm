param(
    [Parameter(Mandatory=$true)][ValidatePattern('^\d+-\d+$')][string]$LeaderBusId,
    [Parameter(Mandatory=$true)][ValidatePattern('^\d+-\d+$')][string]$FollowerBusId,
    [string]$Distro = 'Ubuntu-22.04'
)
$ErrorActionPreference = 'Stop'
if ($LeaderBusId -eq $FollowerBusId) { throw 'Specify two different USB bus IDs.' }
wsl.exe -d $Distro -- /bin/true
if ($LASTEXITCODE -ne 0) { throw "Could not start $Distro." }
foreach ($busId in @($LeaderBusId, $FollowerBusId)) {
    $listing = usbipd list
    if ($LASTEXITCODE -ne 0) { throw 'usbipd list failed.' }
    $row = $listing | Where-Object { $_ -match "^\s*$busId\s+1a86:55d3\s+" }
    if (-not $row) { throw "No CH343 adapter found at $busId. Check usbipd list." }
    if ($row -match '\sAttached\s*$') { continue }
    if ($row -notmatch '\sShared\s*$' -or $row -match '\sNot shared\s*$') {
        throw "Adapter $busId is not shared. Bind it once in administrator PowerShell."
    }
    usbipd attach --wsl --busid $busId
    if ($LASTEXITCODE -ne 0) { throw "Could not attach $busId." }
}
wsl.exe -d $Distro -- ls -l /dev/serial/by-path
