# networkPlus - Windows ag anlik goruntusu (SALT OKUNUR).
#
# Bu betik hicbir ayari DEGISTIRMEZ: yalnizca Get-* cmdlet'leri, Find-NetRoute
# (sorgu), HNetCfg okuma ve `netsh wlan show` kullanir. Yonetici gerektirmez.
#
# Cikti: stdout'a tek satir UTF-8 JSON. Her bolum kendi try/catch'i icindedir;
# bir bolum hata verirse `errors` listesine yazilir, digerleri yine doner.
# Ham veri doner; normalizasyon Python tarafinda yapilir
# (platform/windows/collector.py). Enum'lar metne cevrilir, cunku PS 5.1
# ConvertTo-Json enum'lari sayi olarak yazar.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$out = [ordered]@{}
$errors = New-Object System.Collections.ArrayList
$timings = [ordered]@{}

function Section([string]$name, [scriptblock]$body) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $out[$name] = @(& $body)
    } catch {
        $out[$name] = @()
        [void]$errors.Add([ordered]@{ section = $name; message = "$($_.Exception.Message)".Trim() })
    }
    $timings[$name] = $sw.ElapsedMilliseconds
}

$out.schema = 1
$out.platform = 'windows'
$out.hostname = $env:COMPUTERNAME
$out.taken_at = (Get-Date).ToString('o')
$out.os = [Environment]::OSVersion.Version.ToString()
try {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $out.is_admin = ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
} catch { $out.is_admin = $false }

Section 'adapters' {
    Get-NetAdapter -IncludeHidden | ForEach-Object {
        [ordered]@{
            name        = $_.Name
            description = $_.InterfaceDescription
            guid        = "$($_.InterfaceGuid)"
            index       = [int]$_.ifIndex
            status      = "$($_.Status)"
            admin_status = "$($_.AdminStatus)"
            media_state = "$($_.MediaConnectionState)"
            mac         = $_.MacAddress
            speed       = [uint64]$_.ReceiveLinkSpeed
            media_type  = "$($_.MediaType)"
            physical_media_type = "$($_.PhysicalMediaType)"
            virtual     = [bool]$_.Virtual
            hidden      = [bool]$_.Hidden
            hardware    = [bool]$_.HardwareInterface
            component_id = $_.ComponentID
            driver      = $_.DriverDescription
        }
    }
}

Section 'ip_interfaces' {
    Get-NetIPInterface | ForEach-Object {
        [ordered]@{
            index       = [int]$_.InterfaceIndex
            alias       = $_.InterfaceAlias
            family      = "$($_.AddressFamily)"
            dhcp        = "$($_.Dhcp)"
            metric      = [int]$_.InterfaceMetric
            auto_metric = "$($_.AutomaticMetric)"
            forwarding  = "$($_.Forwarding)"
            mtu         = [uint32]$_.NlMtu
            state       = "$($_.ConnectionState)"
        }
    }
}

Section 'ip_addresses' {
    Get-NetIPAddress | ForEach-Object {
        [ordered]@{
            index   = [int]$_.InterfaceIndex
            address = $_.IPAddress
            prefix  = [int]$_.PrefixLength
            family  = "$($_.AddressFamily)"
            origin  = "$($_.PrefixOrigin)"
            suffix_origin = "$($_.SuffixOrigin)"
            state   = "$($_.AddressState)"
        }
    }
}

Section 'dns' {
    Get-DnsClientServerAddress | Where-Object { $_.ServerAddresses } | ForEach-Object {
        [ordered]@{
            index   = [int]$_.InterfaceIndex
            family  = [int]$_.AddressFamily   # 2 = IPv4, 23 = IPv6
            servers = @($_.ServerAddresses)
        }
    }
}

# DNS elle mi girildi? Get-DnsClientServerAddress bunu soylemez; registry'deki
# NameServer dolu ise elle, bossa DHCP'den (geri alma bunu bilmek zorunda).
Section 'dns_static' {
    $root = 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces'
    Get-ChildItem -Path $root -ErrorAction SilentlyContinue | ForEach-Object {
        $v = Get-ItemProperty -Path $_.PSPath -ErrorAction SilentlyContinue
        [ordered]@{ guid = $_.PSChildName; name_server = "$($v.NameServer)" }
    }
}

# Varsayilan rotalar + VPN'lerin 0/1 + 128/1 "tam tunel" cifti.
Section 'routes' {
    $prefixes = '0.0.0.0/0', '::/0', '0.0.0.0/1', '128.0.0.0/1'
    Get-NetRoute -ErrorAction SilentlyContinue | Where-Object { $prefixes -contains $_.DestinationPrefix } | ForEach-Object {
        [ordered]@{
            index    = [int]$_.InterfaceIndex
            dest     = $_.DestinationPrefix
            next_hop = $_.NextHop
            metric   = [int]$_.RouteMetric
            store    = "$($_.Store)"
        }
    }
}

# Windows'un gercekte sectigi cikis: genel bir adrese giden rota sorgusu.
Section 'internet_route' {
    Find-NetRoute -RemoteIPAddress '8.8.8.8' | Where-Object { $_.DestinationPrefix } | Select-Object -First 1 | ForEach-Object {
        [ordered]@{ index = [int]$_.InterfaceIndex; dest = $_.DestinationPrefix; next_hop = $_.NextHop }
    }
}

Section 'profiles' {
    Get-NetConnectionProfile | ForEach-Object {
        [ordered]@{
            index    = [int]$_.InterfaceIndex
            name     = $_.Name
            category = "$($_.NetworkCategory)"
            ipv4     = "$($_.IPv4Connectivity)"
            ipv6     = "$($_.IPv6Connectivity)"
        }
    }
}

# Yalnizca varsayilan ag gecitlerinin komsu (ARP/ND) kayitlari.
Section 'neighbors' {
    $gws = @($out.routes | Where-Object { $_.next_hop -and $_.next_hop -ne '0.0.0.0' -and $_.next_hop -ne '::' } |
        ForEach-Object { $_.next_hop } | Sort-Object -Unique)
    foreach ($gw in $gws) {
        Get-NetNeighbor -IPAddress $gw -ErrorAction SilentlyContinue | ForEach-Object {
            [ordered]@{ index = [int]$_.InterfaceIndex; ip = $_.IPAddress; mac = $_.LinkLayerAddress; state = "$($_.State)" }
        }
    }
}

Section 'bindings' {
    Get-NetAdapterBinding -IncludeHidden -AllBindings -ComponentID ms_bridge, vms_pp, ms_tcpip, ms_tcpip6, ms_server, ms_msclient -ErrorAction SilentlyContinue |
        ForEach-Object {
            [ordered]@{ name = $_.Name; component = $_.ComponentID; enabled = [bool]$_.Enabled }
        }
}

# Surucunun "Gelismis" sekmesi (aygit yoneticisindeki liste): yalniz gorunen (DisplayName'li)
# ozellikler. Ad/deger surucunun dilindedir -> yalniz gosterim; kimlik RegistryKeyword.
Section 'advanced' {
    Get-NetAdapterAdvancedProperty -Name * -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName } |
        ForEach-Object {
            [ordered]@{
                name     = $_.Name
                display  = $_.DisplayName
                value    = $_.DisplayValue
                keyword  = $_.RegistryKeyword
                registry = @($_.RegistryValue)
                options  = @($_.ValidDisplayValues)
                default  = $_.DefaultDisplayValue
                min      = $_.NumericParameterMinValue
                max      = $_.NumericParameterMaxValue
                step     = $_.NumericParameterStepValue
            }
        }
}

# ICS: HNetCfg okuma (yetki gerektirmez). SharingConnectionType 0 = public, 1 = private.
Section 'ics' {
    $m = New-Object -ComObject HNetCfg.HNetShare
    foreach ($c in $m.EnumEveryConnection) {
        $p = $m.NetConnectionProps.Invoke($c)
        $s = $m.INetSharingConfigurationForINetConnection.Invoke($c)
        [ordered]@{
            name    = $p.Name
            guid    = "$($p.Guid)"
            device  = $p.DeviceName
            enabled = [bool]$s.SharingEnabled
            type    = [int]$s.SharingConnectionType
        }
    }
}

Section 'services' {
    Get-Service -Name SharedAccess, icssvc -ErrorAction SilentlyContinue | ForEach-Object {
        [ordered]@{ name = $_.Name; status = "$($_.Status)"; start = "$($_.StartType)" }
    }
}

Section 'ics_scope' {
    $k = 'HKLM:\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters'
    $v = Get-ItemProperty -Path $k -ErrorAction SilentlyContinue
    if ($v) { [ordered]@{ scope_address = $v.ScopeAddress } }
}

# netsh ciktisi yerellestirilmistir: yalnizca dile bagli olmayan 'SSID' ve
# 'BSSID' anahtarlari ile yuzde isaretli satir kullanilir.
Section 'wlan' {
    # netsh ciktisinin ANAHTARLARI isletim sistemi dilinde ("Name"/"Ad"/"Nom"/"Имя"...).
    # Dile bagli olmayanlar kullanilir: bloklar bos satirla ayrilir, arayuz GUID ile
    # eslenir, 'SSID'/'BSSID' anahtarlari ve yuzde isaretli sinyal satiri evrenseldir.
    $cur = $null
    foreach ($line in (netsh wlan show interfaces)) {
        if (-not $line.Trim()) {
            if ($cur -and $cur.guid) { $cur }
            $cur = $null
            continue
        }
        if ($line -notmatch ':') { continue }
        if (-not $cur) { $cur = [ordered]@{ guid = $null; ssid = $null; bssid = $null; signal = $null } }
        if ($line -match '^\s*GUID\s*:\s*([0-9A-Fa-f-]{36})\s*$') {
            $cur.guid = '{' + $Matches[1].ToUpper() + '}'
        } elseif ($line -match '^\s*SSID\s*:\s*(.*)$') {
            $cur.ssid = $Matches[1].Trim()
        } elseif ($line -match '^\s*BSSID\s*:\s*(.*)$') {
            $cur.bssid = $Matches[1].Trim()
        } elseif ($line -match ':\s*(\d{1,3})\s*%\s*$') {
            $cur.signal = [int]$Matches[1]
        }
    }
    if ($cur -and $cur.guid) { $cur }
}

Section 'vpn' {
    @(Get-VpnConnection -ErrorAction SilentlyContinue) + @(Get-VpnConnection -AllUserConnection -ErrorAction SilentlyContinue) |
        Where-Object { $_ } | ForEach-Object {
            [ordered]@{
                name   = $_.Name
                server = $_.ServerAddress
                status = "$($_.ConnectionStatus)"
                split  = [bool]$_.SplitTunneling
                tunnel = "$($_.TunnelType)"
            }
        }
}

Section 'nat' {
    Get-NetNat | ForEach-Object {
        [ordered]@{ name = $_.Name; internal_prefix = $_.InternalIPInterfaceAddressPrefix; active = [bool]$_.Active }
    }
}

# Hyper-V modulu yoksa sessizce bos doner (hata sayilmaz).
Section 'vm_switches' {
    if (Get-Command Get-VMSwitch -ErrorAction SilentlyContinue) {
        Get-VMSwitch | ForEach-Object {
            [ordered]@{
                name   = $_.Name
                type   = "$($_.SwitchType)"
                uplink = $_.NetAdapterInterfaceDescription
                management_os = [bool]$_.AllowManagementOS
            }
        }
    }
}

$out.errors = @($errors)
$out.timings_ms = $timings
$out | ConvertTo-Json -Depth 6 -Compress
