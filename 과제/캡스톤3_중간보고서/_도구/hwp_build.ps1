param(
  [Parameter(Mandatory=$true)][string]$Html,
  [Parameter(Mandatory=$true)][string]$OutBase,
  [int]$TimeoutSec = 600,
  [int]$HideCoverPageNum = 0
)
# Opens the HTML in Hancom HWP (Open does not raise the encoding dialog that InsertFile raises),
# sets page margins, turns paragraph markers into paragraph shapes, adds page numbers, saves HWP + PDF.
# This file is ASCII only on purpose (Windows PowerShell 5.1 misreads UTF-8 without BOM).
$log = "$OutBase.log"
Remove-Item $log -ErrorAction SilentlyContinue
$before = @(Get-Process Hwp,Hword -ErrorAction SilentlyContinue | ForEach-Object Id)
if ($before.Count -gt 0) { "SKIP: a Hancom editor is already open"; exit 2 }
$job = Start-Job -ScriptBlock { param($h,$o,$log,$hideCover)
  function L($m){ [IO.File]::AppendAllText($log, ((Get-Date -Format 'HH:mm:ss.fff') + ' ' + $m + "`r`n")) }
  $c = [string][char]0xA4
  try {
    L 'create'; $hwp = New-Object -ComObject HWPFrame.HwpObject
    [void]$hwp.SetMessageBoxMode(0x00011011)
    L 'open'; $x = $hwp.Open($h, 'HTML', ''); L "open=$x pages=$($hwp.PageCount)"
    if (-not $x) { throw 'open failed' }

    L 'pagesetup'
    $sd = $hwp.HParameterSet.HSecDef
    [void]$hwp.HAction.GetDefault('PageSetup', $sd.HSet)
    $sd.PageDef.LeftMargin   = $hwp.MiliToHwpUnit(20.0)
    $sd.PageDef.RightMargin  = $hwp.MiliToHwpUnit(20.0)
    $sd.PageDef.TopMargin    = $hwp.MiliToHwpUnit(20.0)
    $sd.PageDef.BottomMargin = $hwp.MiliToHwpUnit(15.0)
    $sd.PageDef.HeaderLen    = $hwp.MiliToHwpUnit(0.0)
    $sd.PageDef.FooterLen    = $hwp.MiliToHwpUnit(10.0)
    [void]$sd.HSet.SetItem('ApplyClass', 24)
    [void]$sd.HSet.SetItem('ApplyTo', 3)
    $x = $hwp.HAction.Execute('PageSetup', $sd.HSet); L "pagesetup=$x pages=$($hwp.PageCount)"

    # marker -> (page break before, keep with next, space before pt, space after pt); -1 = leave as is
    $marks = [ordered]@{ 'H1' = @(1,1,0,10); 'H2' = @(0,1,14,6); 'H3' = @(0,1,10,4); 'C' = @(0,1,8,3); 'K' = @(0,1,-1,-1); 'P' = @(1,0,-1,-1); 'Q' = @(1,1,0,6) }
    foreach ($m in $marks.Keys) {
      $cfg = $marks[$m]; $n = 0
      [void]$hwp.Run('MoveDocBegin')
      for ($i = 0; $i -lt 400; $i++) {
        $fr = $hwp.HParameterSet.HFindReplace
        [void]$hwp.HAction.GetDefault('RepeatFind', $fr.HSet)
        $fr.FindString = $c + $m + $c; $fr.Direction = 0; $fr.IgnoreMessage = 1; $fr.FindType = 1
        if (-not $hwp.HAction.Execute('RepeatFind', $fr.HSet)) { break }
        [void]$hwp.Run('Delete')
        $ps = $hwp.HParameterSet.HParaShape
        [void]$hwp.HAction.GetDefault('ParagraphShape', $ps.HSet)
        if ($cfg[0]) { $ps.PagebreakBefore = 1 }
        if ($cfg[1]) { $ps.KeepWithNext = 1 }
        if ($cfg[2] -ge 0) { $ps.PrevSpacing = [int]($cfg[2] * 100) }
        if ($cfg[3] -ge 0) { $ps.NextSpacing = [int]($cfg[3] * 100) }
        [void]$hwp.HAction.Execute('ParagraphShape', $ps.HSet)
        $n++
      }
      L "marker $m = $n"
    }


    # table policy file: one letter per table in document order
    #   K = inline table (treat as character: moves to the next page as a whole, together with its caption),
    #   C = split between rows only, T = keep + center horizontally (cover table), N / S = leave as is
    L 'tables'
    try {
      $policy = ''
      if (Test-Path "$h.tables") { $policy = ([IO.File]::ReadAllText("$h.tables")).Trim() }
      $ctrl = $hwp.HeadCtrl; $nt = 0; $done = @{}
      while ($ctrl -ne $null) {
        if ($ctrl.CtrlID -eq 'tbl') {
          $k = 'C'
          if ($nt -lt $policy.Length) { $k = [string]$policy[$nt] }
          if ($k -ne 'N' -and $k -ne 'S') {
            $p = $ctrl.Properties
            if ($k -eq 'C') { [void]$p.SetItem('PageBreak', 1) }
            if ($k -eq 'K') { [void]$p.SetItem('TreatAsChar', 1) }
            if ($k -eq 'T') { [void]$p.SetItem('PageBreak', 0); [void]$p.SetItem('HorzAlign', 1) }
            $ctrl.Properties = $p
          }
          $done[$k] = 1 + [int]$done[$k]
          $nt++
        }
        $ctrl = $ctrl.Next
      }
      L "tables=$nt policy=$($policy.Length) :: $(($done.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ' ')"
    } catch { L "tables ERR $($_.Exception.Message)" }

    L 'pagenum'
    [void]$hwp.Run('MoveDocBegin')
    $pn = $hwp.HParameterSet.HPageNumPos
    [void]$hwp.HAction.GetDefault('PageNumPos', $pn.HSet)
    $pn.DrawPos = 5
    $x = $hwp.HAction.Execute('PageNumPos', $pn.HSet); L "pagenum=$x"
    if ($hideCover) {
      try {
        [void]$hwp.Run('MoveDocBegin')
        $ph = $hwp.HParameterSet.HPageHiding
        [void]$hwp.HAction.GetDefault('PageHiding', $ph.HSet)
        $ph.Fields = 32
        $x = $hwp.HAction.Execute('PageHiding', $ph.HSet); L "pagehiding=$x"
      } catch { L "pagehiding ERR $($_.Exception.Message)" }
    }

    L "pages=$($hwp.PageCount)"
    $x = $hwp.SaveAs("$o.hwp", 'HWP', ''); L "saveHwp=$x"
    $x = $hwp.SaveAs("$o.pdf", 'PDF', ''); L "savePdf=$x"
    $hwp.Clear(1); $hwp.Quit(); L 'quit'
  } catch { L "ERROR $($_.Exception.Message)" }
} -ArgumentList $Html,$OutBase,$log,$HideCoverPageNum
if (Wait-Job $job -Timeout $TimeoutSec) { 'job finished' } else { "TIMEOUT after $TimeoutSec s"; Stop-Job $job }
Remove-Job $job -Force
Get-Content $log -ErrorAction SilentlyContinue
$new = @(Get-Process Hwp,Hword,HimTrayIcon -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id })
foreach($p in $new){ Stop-Process -Id $p.Id -Force -Confirm:$false }
