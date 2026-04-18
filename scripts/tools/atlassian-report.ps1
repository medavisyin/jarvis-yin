# atlassian-report.ps1 - Single-script Atlassian daily report generator
# Runs Jira + Confluence queries, generates markdown report, outputs summary
# Usage: powershell -ExecutionPolicy Bypass -File atlassian-report.ps1 [-ReportDir "d:\projects\docs"]

param(
    [string]$ReportDir = "d:\projects\docs"
)

$ErrorActionPreference = "Stop"

# --- 1. Read credentials from environment variables ---
$site = $env:ATLASSIAN_SITE
$email = $env:ATLASSIAN_EMAIL
$token = $env:ATLASSIAN_API_TOKEN

if (-not $site -or -not $email -or -not $token) {
    Write-Output "ERROR: Missing environment variables. Set ATLASSIAN_SITE, ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN"
    exit 1
}

$auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${email}:${token}"))
$baseHeaders = @{ "Authorization" = "Basic $auth"; "Accept" = "application/json" }
$today = Get-Date -Format "yyyyMMdd"
$todayDisplay = Get-Date -Format "dddd, MMMM d, yyyy"

# --- 2. Run Jira + Confluence queries in parallel ---
$jiraJob = Start-Job -ScriptBlock {
    param($site, $auth)
    $headers = @{ "Authorization" = "Basic $auth"; "Accept" = "application/json"; "Content-Type" = "application/json" }
    $body = @{
        jql = "assignee = currentUser() AND status != Done AND resolution = Unresolved ORDER BY priority DESC, updated DESC"
        fields = @("key","summary","status","priority","created","updated","reporter","description","issuetype","project","labels","components","parent","customfield_10020")
        maxResults = 50
    } | ConvertTo-Json
    try {
        $r = Invoke-RestMethod -Uri "https://${site}/rest/api/3/search/jql" -Headers $headers -Method Post -Body $body
        $r | ConvertTo-Json -Depth 15 -Compress
    } catch {
        Write-Output "JIRA_ERROR: $($_.Exception.Message)"
    }
} -ArgumentList $site, $auth

$confluenceJob = Start-Job -ScriptBlock {
    param($site, $auth)
    $headers = @{ "Authorization" = "Basic $auth"; "Accept" = "application/json" }
    $cql = '(creator = "712020:369e5fbe-a6fa-41c4-b613-627278451b0c" OR creator = "712020:1d619c3c-b980-4bac-9966-ee62b9f7bd11" OR creator = "712020:f85eabdc-dd64-43d1-afa6-72c9c6b65f11" OR creator = "712020:4babc3e7-a282-4e31-a84b-233078fdd451" OR creator = "712020:afcd5f1a-f4d5-40c2-a255-f62c7e484cb6") AND type = page AND (lastModified >= now("-7d") OR created >= now("-7d")) ORDER BY lastModified DESC'
    $encodedCql = [uri]::EscapeDataString($cql)
    # Include body.storage so we can generate per-page summaries in the final markdown report.
    # This increases payload size but keeps the skill to a single command/request.
    $uri = "https://${site}/wiki/rest/api/content/search?cql=${encodedCql}&limit=20&expand=space,history,history.lastUpdated,version,body.storage"
    try {
        $r = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get
        $r | ConvertTo-Json -Depth 15 -Compress
    } catch {
        Write-Output "CONFLUENCE_ERROR: $($_.Exception.Message)"
    }
} -ArgumentList $site, $auth

# Wait for both jobs
$jiraResult = Receive-Job -Job $jiraJob -Wait -AutoRemoveJob
$confluenceResult = Receive-Job -Job $confluenceJob -Wait -AutoRemoveJob

# --- 3. Parse results ---
$jiraData = $null
$confluenceData = $null
$jiraError = $null
$confluenceError = $null

if ($jiraResult -match "^JIRA_ERROR:") {
    $jiraError = $jiraResult
} else {
    try { $jiraData = $jiraResult | ConvertFrom-Json } catch { $jiraError = "Failed to parse Jira response" }
}

if ($confluenceResult -match "^CONFLUENCE_ERROR:") {
    $confluenceError = $confluenceResult
} else {
    try { $confluenceData = $confluenceResult | ConvertFrom-Json } catch { $confluenceError = "Failed to parse Confluence response" }
}

# --- 4. Helper: extract text from ADF description ---
function Get-AdfText($node) {
    $texts = @()
    if ($null -eq $node) { return "" }
    if ($node.type -eq "text" -and $node.text) { $texts += $node.text }
    if ($node.content) {
        foreach ($child in $node.content) { $texts += (Get-AdfText $child) }
    }
    return ($texts -join " ").Trim()
}

# --- 4b. Helper: extract summary/topics from Confluence storage (XHTML) ---
function Normalize-Whitespace([string]$text) {
    if (-not $text) { return "" }
    $t = $text -replace "\u00A0", " "  # nbsp
    $t = $t -replace "\s+", " "
    return $t.Trim()
}

function Strip-Html([string]$html) {
    if (-not $html) { return "" }
    try {
        $decoded = [System.Net.WebUtility]::HtmlDecode($html)
    } catch {
        $decoded = $html
    }
    $noTags = $decoded -replace "<[^>]+>", " "
    return (Normalize-Whitespace $noTags)
}

function Get-HeadingsFromStorage([string]$html, [int]$max = 6) {
    if (-not $html) { return @() }
    $list = New-Object System.Collections.Generic.List[string]
    $decoded = $html
    try { $decoded = [System.Net.WebUtility]::HtmlDecode($html) } catch {}

    $matches = [regex]::Matches($decoded, "<h[1-3][^>]*>(.*?)</h[1-3]>", [System.Text.RegularExpressions.RegexOptions]::IgnoreCase -bor [System.Text.RegularExpressions.RegexOptions]::Singleline)
    foreach ($m in $matches) {
        if ($list.Count -ge $max) { break }
        $inner = $m.Groups[1].Value
        $heading = Strip-Html $inner
        if ($heading -and -not $list.Contains($heading)) {
            $list.Add($heading)
        }
    }
    return @($list)
}

function Get-PageSummaryFromStorage([string]$html, [int]$maxChars = 400) {
    $text = Strip-Html $html
    if (-not $text) { return "" }
    if ($text.Length -le $maxChars) { return $text }
    return ($text.Substring(0, $maxChars) + "...")
}

# --- 5. Build markdown report ---
$md = @()
$md += "# Atlassian Daily Report"
$md += ""
$md += "**Generated:** $todayDisplay"
$md += "**User:** $email"
$md += ""
$md += "---"
$md += ""

# --- Jira Section ---
$issues = @()
if ($jiraData -and $jiraData.issues) { $issues = @($jiraData.issues) }
$issueCount = $issues.Count

$md += "## Summary"
$md += ""
$md += "- **Jira**: $issueCount open ticket(s)"
$md += "- **Confluence**: (see below) pages updated in last 7 days"
$md += ""
$md += "---"
$md += ""

$md += "## Open Jira Tickets Assigned to Me ($issueCount tickets)"
$md += ""

# Summary table for quick view
$summaryLines = @()
$summaryLines += "| Key | Summary | Priority | Type | Status | Sprint |"
$summaryLines += "|-----|---------|----------|------|--------|--------|"

foreach ($issue in $issues) {
    $key = $issue.key
    $f = $issue.fields
    $summary = $f.summary
    $typeName = $f.issuetype.name
    $projectName = $f.project.name
    $statusName = $f.status.name
    $priorityName = if ($f.priority) { $f.priority.name } else { "None" }
    $created = ($f.created -split "T")[0]
    $updated = ($f.updated -split "T")[0]
    $reporterName = if ($f.reporter) { $f.reporter.displayName } else { "Unknown" }
    $sprintName = ""
    if ($f.customfield_10020 -and $f.customfield_10020.Count -gt 0) {
        $sprintName = $f.customfield_10020[0].name
    }
    $epicInfo = ""
    if ($f.parent) {
        $epicInfo = "[$($f.parent.key)](https://${site}/browse/$($f.parent.key)) - $($f.parent.fields.summary)"
    }

    # Summary table row
    $summaryLines += "| [$key](https://${site}/browse/$key) | $summary | $priorityName | $typeName | $statusName | $sprintName |"

    # Detailed section
    $md += "### [$key](https://${site}/browse/$key) - $summary"
    $md += ""
    $md += "| Field | Value |"
    $md += "|-------|-------|"
    $md += "| **Type** | $typeName |"
    $md += "| **Project** | $projectName |"
    $md += "| **Status** | $statusName |"
    $md += "| **Priority** | $priorityName |"
    if ($sprintName) { $md += "| **Sprint** | $sprintName |" }
    if ($epicInfo) { $md += "| **Epic** | $epicInfo |" }
    $md += "| **Created** | $created |"
    $md += "| **Updated** | $updated |"
    $md += "| **Reporter** | $reporterName |"
    $md += ""

    # Description
    $desc = ""
    if ($f.description) {
        $desc = Get-AdfText $f.description
        if ($desc.Length -gt 500) { $desc = $desc.Substring(0, 500) + "..." }
    }
    if ($desc) {
        $md += "**Description:** $desc"
        $md += ""
    }
    $md += "---"
    $md += ""
}

# --- Confluence Section ---
$pages = @()
if ($confluenceData -and $confluenceData.results) { $pages = @($confluenceData.results) }
$pageCount = $pages.Count

$md += "## Team Confluence Updates (Last 7 Days) - $pageCount pages"
$md += ""

$authorCounts = @{}
$spaceCounts = @{}

foreach ($page in $pages) {
    $title = $page.title
    $spaceName = $page.space.name
    $spaceKey = $page.space.key
    $webui = $page._links.webui
    $link = "https://${site}/wiki${webui}"

    $creatorName = $page.history.createdBy.publicName
    $updatedBy = ""
    $updatedWhen = ""
    if ($page.history.lastUpdated) {
        $updatedBy = $page.history.lastUpdated.by.publicName
        $updatedWhen = ($page.history.lastUpdated.when -split "T")[0]
    } elseif ($page.version) {
        $updatedBy = $page.version.by.publicName
        $updatedWhen = ($page.version.when -split "T")[0]
    }
    $versionNum = if ($page.version) { $page.version.number } else { "?" }

    # Extract per-page summary/details (requires body.storage in the query expand)
    $storageHtml = ""
    if ($page.body -and $page.body.storage -and $page.body.storage.value) {
        $storageHtml = [string]$page.body.storage.value
    }
    $pageSummary = Get-PageSummaryFromStorage -html $storageHtml -maxChars 450
    $topics = Get-HeadingsFromStorage -html $storageHtml -max 6

    # Track stats
    if ($updatedBy) {
        if (-not $authorCounts.ContainsKey($updatedBy)) { $authorCounts[$updatedBy] = 0 }
        $authorCounts[$updatedBy]++
    }
    if ($spaceName) {
        $sKey = "$spaceName ($spaceKey)"
        if (-not $spaceCounts.ContainsKey($sKey)) { $spaceCounts[$sKey] = 0 }
        $spaceCounts[$sKey]++
    }

    $md += "### [$title]($link)"
    $md += "**Space:** $spaceName | **Updated:** $updatedWhen | **By:** $updatedBy | **v$versionNum**"
    $md += ""

    if ($pageSummary) {
        $md += "**Summary:** $pageSummary"
        $md += ""
    } else {
        # Keep ASCII here to avoid any encoding/parser surprises in PowerShell.
        $md += "**Summary:** *(No extractable text - page may be mostly images/macros)*"
        $md += ""
    }

    if ($topics -and $topics.Count -gt 0) {
        $md += "**Key topics (headings):**"
        foreach ($t in $topics) {
            $md += "- $t"
        }
        $md += ""
    }

    $md += "---"
    $md += ""
}

# --- Statistics ---
$md += "## Summary"
$md += ""
$md += "### Jira"
$md += "| Metric | Value |"
$md += "|--------|-------|"
$md += "| Total Open | $issueCount |"

$priorityGroups = $issues | Group-Object { $_.fields.priority.name } | Sort-Object Name
foreach ($g in $priorityGroups) {
    $md += "| $($g.Name) | $($g.Count) |"
}
$md += ""

$md += "### Confluence by Author"
$md += "| Author | Pages |"
$md += "|--------|-------|"
foreach ($a in ($authorCounts.GetEnumerator() | Sort-Object Value -Descending)) {
    $md += "| $($a.Key) | $($a.Value) |"
}
$md += ""

$md += "### Confluence by Space"
$md += "| Space | Pages |"
$md += "|-------|-------|"
foreach ($s in ($spaceCounts.GetEnumerator() | Sort-Object Value -Descending)) {
    $md += "| $($s.Key) | $($s.Value) |"
}

# --- 6. Write report file ---
if (-not (Test-Path $ReportDir)) { New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null }
$reportPath = Join-Path $ReportDir "atlassian-daily-report-${today}.md"
$md -join "`n" | Set-Content -Path $reportPath -Encoding UTF8

# --- 7. Output summary to stdout (this is what the AI displays) ---
Write-Output "=== ATLASSIAN DAILY REPORT ==="
Write-Output "Report saved: $reportPath"
Write-Output ""
Write-Output "## JIRA - $issueCount Open Tickets"
if ($jiraError) { Write-Output "  ERROR: $jiraError" }
$summaryLines | ForEach-Object { Write-Output $_ }
Write-Output ""
Write-Output "## CONFLUENCE - $pageCount Pages Updated (Last 7 Days)"
if ($confluenceError) { Write-Output "  ERROR: $confluenceError" }
foreach ($page in $pages) {
    $updatedBy = ""
    $updatedWhen = ""
    if ($page.history.lastUpdated) {
        $updatedBy = $page.history.lastUpdated.by.publicName
        $updatedWhen = ($page.history.lastUpdated.when -split "T")[0]
    } elseif ($page.version) {
        $updatedBy = $page.version.by.publicName
        $updatedWhen = ($page.version.when -split "T")[0]
    }
    $webui = $page._links.webui
    # Short summary hint (first 120 chars) for quick scanning in stdout
    $storageHtml = ""
    if ($page.body -and $page.body.storage -and $page.body.storage.value) {
        $storageHtml = [string]$page.body.storage.value
    }
    $short = Get-PageSummaryFromStorage -html $storageHtml -maxChars 120
    if ($short) {
        Write-Output "- [$($page.title)](https://${site}/wiki${webui}) | $updatedBy | $updatedWhen | $short"
    } else {
        Write-Output "- [$($page.title)](https://${site}/wiki${webui}) | $updatedBy | $updatedWhen"
    }
}
Write-Output ""
Write-Output "## STATS"
Write-Output "Authors: $(($authorCounts.GetEnumerator() | Sort-Object Value -Descending | ForEach-Object { "$($_.Key)($($_.Value))" }) -join ', ')"
Write-Output "Spaces: $(($spaceCounts.GetEnumerator() | Sort-Object Value -Descending | ForEach-Object { "$($_.Key)($($_.Value))" }) -join ', ')"
