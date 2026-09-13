$tunneldPortOpen = $false
try {
    $client = New-Object System.Net.Sockets.TcpClient
    $connectTask = $client.BeginConnect('127.0.0.1', 49151, $null, $null)
    if ($connectTask.AsyncWaitHandle.WaitOne(500) -and $client.Connected) {
        $tunneldPortOpen = $true
    }
    $client.Close()
} catch {
    $tunneldPortOpen = $false
}

if ($tunneldPortOpen) {
    exit 0
}

Start-Process -FilePath 'python' -ArgumentList '-m pymobiledevice3 remote tunneld' -Verb RunAs
exit 1
