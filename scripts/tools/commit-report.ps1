param(
    [int]$Hours = 48,
    [string]$OutputDir = $(if ($env:JARVIS_REPORTS_ROOT) { $env:JARVIS_REPORTS_ROOT } else { "C:/reports/ai" })
)

$ErrorActionPreference = "Continue"
$OutputEncoding = [System.Text.Encoding]::UTF8

$repos = @(
    @{name="P4M Next"; path="d:/projects/p4m"},
    @{name="Admin App"; path="d:/projects/admin-app"},
    @{name="Core Framework"; path="d:/projects/core-framework"},
    @{name="Vaadin UI"; path="d:/projects/vaadin-ui"},
    @{name="AWS Infrastructure P4M EKS"; path="d:/p4m_cloud_project/aws-infra-p4m-eks"},
    @{name="RIS Utilization Dashboard"; path="D:/cto/scm/ris-utilization-dashboard"},
    @{name="B4M Next"; path="d:/projects/b4m.next"},
    @{name="Application Server"; path="d:/projects/applicationserver"},
    @{name="Apache Dist"; path="d:/projects/apache-dist"},
    @{name="Communication Stack"; path="d:/projects/communication-stack"},
    @{name="Identity Server"; path="d:/projects/identityserver"},
    @{name="Keycloak"; path="d:/projects/keycloak"},
    @{name="Local Gateway"; path="d:/projects/local-gateway"},
    @{name="Local Gateway Plugins"; path="d:/projects/local-gateway-plugins"},
    @{name="Parent"; path="d:/projects/parent"},
    @{name="SMS Service"; path="d:/projects/sms-service"},
    @{name="SMS Service Client"; path="d:/projects/sms-service-client"},
    @{name="Teleradiology Cloud Backend"; path="d:/projects/teleradiology-cloud-backend"}
)

$since = (Get-Date).AddHours(-$Hours).ToString("yyyy-MM-ddTHH:mm:ss")
$today = Get-Date -Format "yyyy-MM-dd"
$reportFile = Join-Path $OutputDir "$today/commit-report-$today.md"

$allCommits = @()
$repoStats = @()
$totalCommits = 0
$activeRepos = 0

foreach ($repo in $repos) {
    $repoPath = $repo.path
    $repoName = $repo.name
    if (-not (Test-Path $repoPath)) { continue }
    if (-not (Test-Path "$repoPath/.git")) { continue }

    Push-Location $repoPath
    try {
        git fetch --all --prune 2>$null | Out-Null

        $logOutput = git --no-pager log --all --since="$since" `
            --pretty=format:"%H|%an|%ae|%ad|%s" --date=iso 2>$null

        if (-not $logOutput) {
            $repoStats += @{name=$repoName; commits=0; authors=@()}
            Pop-Location
            continue
        }

        $lines = $logOutput -split "`n" | Where-Object { $_ -match '\S' }
        $seenHashes = @{}
        $repoCommits = @()
        $repoAuthors = @{}

        foreach ($line in $lines) {
            $parts = $line -split '\|', 5
            if ($parts.Count -lt 5) { continue }
            $hash = $parts[0].Trim()
            if ($seenHashes.ContainsKey($hash)) { continue }
            $seenHashes[$hash] = $true

            $author = $parts[1].Trim()
            $email = $parts[2].Trim()
            $date = $parts[3].Trim()
            $msg = $parts[4].Trim()

            if (-not $repoAuthors.ContainsKey($author)) { $repoAuthors[$author] = 0 }
            $repoAuthors[$author]++

            $stat = git --no-pager show --shortstat --format="" $hash 2>$null
            $filesChanged = 0; $insertions = 0; $deletions = 0
            if ($stat -match '(\d+) file') { $filesChanged = [int]$matches[1] }
            if ($stat -match '(\d+) insertion') { $insertions = [int]$matches[1] }
            if ($stat -match '(\d+) deletion') { $deletions = [int]$matches[1] }

            $remoteUrl = git config --get remote.origin.url 2>$null
            $commitUrl = ""
            if ($remoteUrl -match 'scm/([^/]+)/([^/.]+)') {
                $project = $matches[1].ToUpper()
                $repoSlug = $matches[2]
                $commitUrl = "https://git.medavis.local/projects/$project/repos/$repoSlug/commits/$hash"
            }

            $repoCommits += @{
                repo=$repoName; hash=$hash; author=$author; email=$email
                date=$date; message=$msg; files=$filesChanged
                insertions=$insertions; deletions=$deletions; url=$commitUrl
            }
        }

        $allCommits += $repoCommits
        $count = $repoCommits.Count
        $totalCommits += $count
        if ($count -gt 0) { $activeRepos++ }
        $repoStats += @{name=$repoName; commits=$count; authors=$repoAuthors.Keys}
    } finally {
        Pop-Location
    }
}

$authorStats = @{}
foreach ($c in $allCommits) {
    $a = $c.author
    if (-not $authorStats.ContainsKey($a)) {
        $authorStats[$a] = @{commits=0; insertions=0; deletions=0; repos=@{}}
    }
    $authorStats[$a].commits++
    $authorStats[$a].insertions += $c.insertions
    $authorStats[$a].deletions += $c.deletions
    $authorStats[$a].repos[$c.repo] = $true
}

$sb = [System.Text.StringBuilder]::new()
[void]$sb.AppendLine("# Multi-Repository Commit Report")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("**Generated**: $(Get-Date -Format 'yyyy-MM-dd HH:mm')")
[void]$sb.AppendLine("**Time Range**: Last $Hours hours (since $since)")
[void]$sb.AppendLine("**Repositories Scanned**: $($repos.Count)")
[void]$sb.AppendLine("**Active Repositories**: $activeRepos")
[void]$sb.AppendLine("**Total Commits**: $totalCommits")
[void]$sb.AppendLine("**Unique Authors**: $($authorStats.Count)")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("---")
[void]$sb.AppendLine("")

[void]$sb.AppendLine("## Author Summary")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("| Author | Commits | Lines +/- | Repositories |")
[void]$sb.AppendLine("|--------|---------|-----------|--------------|")
$sortedAuthors = $authorStats.GetEnumerator() | Sort-Object { $_.Value.commits } -Descending
foreach ($entry in $sortedAuthors) {
    $a = $entry.Key
    $v = $entry.Value
    $repoList = ($v.repos.Keys | Sort-Object) -join ", "
    [void]$sb.AppendLine("| $a | $($v.commits) | +$($v.insertions)/-$($v.deletions) | $repoList |")
}
[void]$sb.AppendLine("")

[void]$sb.AppendLine("## Repository Activity")
[void]$sb.AppendLine("")
foreach ($rs in ($repoStats | Sort-Object { $_.commits } -Descending)) {
    $icon = if ($rs.commits -gt 10) { "HIGH" } elseif ($rs.commits -gt 0) { "ACTIVE" } else { "QUIET" }
    [void]$sb.AppendLine("### $($rs.name) ($icon - $($rs.commits) commits)")
    [void]$sb.AppendLine("")
    if ($rs.commits -eq 0) {
        [void]$sb.AppendLine("No commits in the last $Hours hours.")
        [void]$sb.AppendLine("")
        continue
    }
    $repoC = $allCommits | Where-Object { $_.repo -eq $rs.name } | Sort-Object { $_.date } -Descending
    foreach ($c in $repoC) {
        $shortHash = $c.hash.Substring(0, 10)
        $link = if ($c.url) { "[$shortHash]($($c.url))" } else { "``$shortHash``" }
        [void]$sb.AppendLine("- $link **$($c.author)** ($($c.date.Substring(0,16))): $($c.message) (+$($c.insertions)/-$($c.deletions), $($c.files) files)")
    }
    [void]$sb.AppendLine("")
}

$dir = Split-Path $reportFile -Parent
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
$sb.ToString() | Out-File -FilePath $reportFile -Encoding utf8

Write-Output "COMMIT_REPORT_DONE"
Write-Output "Total: $totalCommits commits across $activeRepos active repos ($($authorStats.Count) authors)"
Write-Output "Report: $reportFile"
Write-Output "---DATA_START---"
Write-Output $sb.ToString()
Write-Output "---DATA_END---"
