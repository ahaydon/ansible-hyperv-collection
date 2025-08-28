#!powershell

#Requires -Module Ansible.ModuleUtils.Legacy

$ErrorActionPreference = "Stop"

$params = Parse-Args $args -supports_check_mode $true;

$vhdPath = Get-AnsibleParam -obj $params -name vhd_path
$vhdParentPath = Get-AnsibleParam -obj $params -name vhd_parent_path
$vhdSizeBytes = Get-AnsibleParam -obj $params -name vhd_size_bytes -default 40GB
$vhdDifferencing = [bool]$vhdParentPath

$vmName = Get-AnsibleParam -obj $params -name name -failifempty $true -emptyattributefailmessage "missing required argument: name"
$cpu = Get-AnsibleParam -obj $params -name cpu -default '1'
$memory = Get-AnsibleParam -obj $params -name memory -default 2048MB
$generation = Get-AnsibleParam -obj $params -name generation -default 2
$switchName = Get-AnsibleParam -obj $params -name switch_name -default $null
$vmGroups = Get-AnsibleParam -obj $params -name group_names
$state = Get-AnsibleParam -obj $params -name state -default "present"

$result = @{
    changed = $false
}


function CreateVM {
    $vm = Get-VM -Name $vmName -ErrorAction SilentlyContinue
    if ($vm) {
        return $vm
    }

    $result.changed = $true

    if (Test-Path -LiteralPath $vhdPath) {
        Remove-Item -LiteralPath $vhdPath -Force
    }

    $vhdParams = @{
        Path = $vhdPath
        ParentPath = $vhdParentPath
        SizeBytes = $vhdSizeBytes
        Differencing = $vhdDifferencing
    }
    $vmParams = @{
        Name = $vmName
        MemoryStartupBytes = $memory
        VHDPath = $vhdPath
        Generation = $generation
        Force = $true
    }
    if ($switchName) {
        $vmParams.SwitchName = $switchName
    }
    $vmSettings = @{
        AutomaticCheckpointsEnabled = $false
        AutomaticStopAction = 'Shutdown'
        CheckpointType = 'Disabled'
        ProcessorCount = $cpu
    }
    New-VHD @vhdParams | Out-Null
    $vm = New-VM @vmParams
    $vm | Set-VM @vmSettings -PassThru
    $vm | Set-VMFirmware -BootOrder $vm.HardDrives[0] | Out-Null
}

function StartVM([Parameter(ValueFromPipeline=$true)]$vm) {
    if ($vm.State -ne 'Running') {
        $result.changed = $true
        Start-VM -VM $vm -PassThru
    }
}

function AssignGroups([Parameter(ValueFromPipeline=$true)]$vm) {
    foreach ($groupName in $vmGroups) {
        if ($groupName -notin $vm.Groups.Name) {
            if (-Not (Get-VMGroup -Name $groupName)) {
                New-VMGroup -Name $groupName -GroupType VMCollectionType | Out-Null
            }
            Add-VMGroupMember -Name $groupName -VM $vm
            $result.changed = $true
        }
    }
    return $vm
}

function WaitForVM([Parameter(ValueFromPipeline=$true)]$vm) {
    while ($true) {
        # Wait until the VM is online and agent is running
        while ((Get-VMIntegrationService -VMName $vmName -Name Heartbeat).PrimaryStatusDescription -ne 'OK') {
            Start-Sleep -Seconds 5
        }

        return $vm
    }
}

function ShutdownVM {
    $vm = Get-VM -Name $vmName -ErrorAction SilentlyContinue
    if ($vm.State -ne 'Off') {
        $result.changed = $true
        Stop-VM -Name $vmName -WarningAction SilentlyContinue
    }
}

function PoweroffVM {
    $vm = Get-VM -Name $vmName -ErrorAction SilentlyContinue
    if ($vm) {
        $result.changed = $true
        Stop-VM -Name $vmName -TurnOff -PassThru -Force -WarningAction SilentlyContinue
    }
}

function DestroyVM([Parameter(ValueFromPipeline=$true)]$vm) {
    if ($vm) {
        $result.changed = $true
        Remove-VM -Name $vmName -Force
    }
    if (Test-Path -LiteralPath $vhdPath) {
        $result.changed = $true
        Remove-Item -LiteralPath $vhdPath -Force
    }
}


switch ($state) {
    "present" { $vm = CreateVM; AssignGroups $vm }
    "running" { $vm = CreateVM; AssignGroups $vm; StartVM $vm; WaitForVM $vm }
    "stopped" { ShutdownVM }
    "poweroff" { PoweroffVM }
    "absent" { $vm = PoweroffVM; DestroyVM $vm }
}

Exit-Json $result
