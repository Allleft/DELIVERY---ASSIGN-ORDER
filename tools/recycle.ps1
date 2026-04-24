[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, ValueFromPipeline = $true, ValueFromPipelineByPropertyName = $true)]
    [Alias("LiteralPath")]
    [string[]]$Path,
    [switch]$WhatIfOnly
)

begin {
    Add-Type -AssemblyName Microsoft.VisualBasic
}

process {
    foreach ($item in $Path) {
        $resolved = Resolve-Path -LiteralPath $item -ErrorAction Stop
        foreach ($target in $resolved) {
            if ($WhatIfOnly) {
                Write-Output "Recycle preview: $($target.Path)"
                continue
            }

            if (Test-Path -LiteralPath $target.Path -PathType Container) {
                [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory(
                    $target.Path,
                    [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
                    [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin
                )
            } else {
                [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
                    $target.Path,
                    [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
                    [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin
                )
            }
            Write-Output "Recycled: $($target.Path)"
        }
    }
}
