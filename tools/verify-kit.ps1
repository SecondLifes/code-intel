<#
.SYNOPSIS
    Mechanical consistency checks for this kit. Run locally before finishing a
    change; run in CI on every push/PR (.github/workflows/verify.yml calls it).

.DESCRIPTION
    Every check here exists because the corresponding failure was actually
    observed in a shipped kit, not because it sounded prudent:

      1. Generator drift      — .claude/rules, .cursor/rules and .claude/commands
                                out of sync with .agents/ because someone edited a
                                generated copy, or forgot to re-run the generator.
      2. Cursor extension     — a rule written as .md under .cursor/rules, which
                                Cursor silently ignores (cursor.com/docs/rules).
      3. Claude skill links   — .claude/skills/ missing an entry, i.e. Claude Code
                                discovering none of this kit's skills.
      4. SKILL.md frontmatter — a `name` the Agent Skills spec rejects (anything
                                but lowercase/digits/hyphen), a missing or
                                over-long `description`.
      5. Unfilled placeholders— a literal [FILL IN marker shipped to users. The
                                .specify/ templates are exempt: their placeholders
                                are the product.
      6. Dead image links     — README embedding docs/images/*.png that isn't there.
      7. LICENSE presence     — a README license badge with no LICENSE file.

    Exits non-zero if any check fails, printing every failure rather than
    stopping at the first one.

.NOTES
    Needs PowerShell 7+ and git. Safe to run repeatedly; changes nothing except
    regenerating the generated folders (which is the point of check 1).
#>

param(
    # In CI the generator must not leave the tree dirty. Locally you may want the
    # regeneration itself to be the fix, so drift is reported but not fatal.
    [switch]$SkipDriftCheck
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$failures = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()

function Add-Failure { param([string]$Check, [string]$Detail) $script:failures.Add("[$Check] $Detail") }
function Add-Warning { param([string]$Check, [string]$Detail) $script:warnings.Add("[$Check] $Detail") }
function Write-Section { param([string]$Name) Write-Host ""; Write-Host "== $Name" -ForegroundColor Cyan }

# --- 1. Generator drift -------------------------------------------------------
Write-Section "Generator drift"
if ($SkipDriftCheck) {
    Write-Host "  skipped (-SkipDriftCheck)"
} else {
    & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'generate-ai-configs.ps1') | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Add-Failure 'drift' "generate-ai-configs.ps1 exited $LASTEXITCODE"
    } else {
        # --porcelain is empty exactly when the working tree matches HEAD.
        $dirty = @(git -C $RepoRoot status --porcelain -- .claude .cursor 2>$null)
        if ($dirty.Count -gt 0) {
            Add-Failure 'drift' "generated files differ from committed ones — run 'pwsh tools/generate-ai-configs.ps1' and commit the result:`n    $($dirty -join "`n    ")"
        } else {
            Write-Host "  OK — generated copies match .agents/"
        }
    }
}

# --- 2. Cursor rule extension -------------------------------------------------
Write-Section "Cursor rule extension"
$cursorRules = Join-Path $RepoRoot '.cursor/rules'
if (Test-Path $cursorRules) {
    $wrongExt = @(Get-ChildItem $cursorRules -File -Recurse | Where-Object { $_.Extension -ne '.mdc' })
    if ($wrongExt.Count -gt 0) {
        Add-Failure 'cursor-ext' "Cursor ignores anything but .mdc under .cursor/rules: $($wrongExt.Name -join ', ')"
    } else {
        Write-Host "  OK — $((Get-ChildItem $cursorRules -File).Count) rule(s), all .mdc"
    }
} else {
    Write-Host "  skipped — no .cursor/rules"
}

# --- 3. Claude skill links ----------------------------------------------------
Write-Section "Claude skill discovery"
$agentsSkills = Join-Path $RepoRoot '.agents/skills'
$claudeSkills = Join-Path $RepoRoot '.claude/skills'
if (Test-Path $agentsSkills) {
    $expected = @(Get-ChildItem $agentsSkills -Directory | Select-Object -ExpandProperty Name)
    $actual   = if (Test-Path $claudeSkills) { @(Get-ChildItem $claudeSkills -Directory -Force | Select-Object -ExpandProperty Name) } else { @() }
    $missing  = @($expected | Where-Object { $_ -notin $actual })
    if ($missing.Count -gt 0) {
        Add-Failure 'skill-links' ".claude/skills/ has no entry for: $($missing -join ', ') — Claude Code discovers skills only there, so these would never trigger."
    } else {
        Write-Host "  OK — $($expected.Count) skill(s) reachable under .claude/skills/"
    }
} else {
    Write-Host "  skipped — no .agents/skills"
}

# --- 4. SKILL.md frontmatter --------------------------------------------------
Write-Section "SKILL.md frontmatter"
$skillCount = 0
if (Test-Path $agentsSkills) {
    Get-ChildItem $agentsSkills -Directory | ForEach-Object {
        $md = Join-Path $_.FullName 'SKILL.md'
        if (-not (Test-Path $md)) { Add-Failure 'skill-md' "$($_.Name)/ has no SKILL.md"; return }
        $skillCount++

        $text = Get-Content $md -Raw
        if ($text -notmatch '(?s)^﻿?---\r?\n(.*?)\r?\n---') {
            Add-Failure 'skill-md' "$($_.Name)/SKILL.md has no YAML frontmatter block"
            return
        }
        $fm = $Matches[1]

        if ($fm -match '(?m)^name:\s*(.+?)\s*$') {
            $name = $Matches[1].Trim().Trim('"').Trim("'")
            # Agent Skills spec: lowercase letters, digits and hyphens only.
            if ($name -cnotmatch '^[a-z0-9]+(-[a-z0-9]+)*$') {
                Add-Failure 'skill-md' "$($_.Name)/SKILL.md name '$name' is not spec-compliant (lowercase letters, digits and hyphens only)"
            }
        } else {
            Add-Failure 'skill-md' "$($_.Name)/SKILL.md frontmatter has no 'name:'"
        }

        if ($fm -match '(?m)^description:\s*(.+?)\s*$') {
            $desc = $Matches[1].Trim()
            # WARNING, not a failure: an over-long description is a real
            # portability risk (it is the string every tool matches against, and
            # some enforce a cap), but no numeric ceiling is stated in the
            # official Claude Code skill docs, so failing a build on an
            # unverified threshold would be worse than flagging it. 1024 is a
            # conservative working limit — raise or drop it if a real spec
            # number turns up.
            if ($desc.Length -gt 1024) {
                Add-Warning 'skill-md' "$($_.Name)/SKILL.md description is $($desc.Length) chars — long enough to risk truncation or rejection by a stricter tool; consider tightening it."
            }
        } else {
            Add-Failure 'skill-md' "$($_.Name)/SKILL.md frontmatter has no 'description:' — without it the model cannot trigger the skill"
        }
    }
    Write-Host "  checked $skillCount SKILL.md file(s)"
}

# --- 5. Unfilled placeholders -------------------------------------------------
Write-Section "Unfilled placeholders"
# .specify/ templates are meant to carry placeholders — they are the deliverable.
$placeholderHits = @(
    Get-ChildItem $RepoRoot -Recurse -File -Include *.md, *.json, *.ps1, *.bat -ErrorAction SilentlyContinue |
        Where-Object {
            $rel = $_.FullName.Substring($RepoRoot.Length + 1).Replace('\', '/')
            # .claude/skills/* is excluded because it is a link farm into
            # .agents/skills — scanning it would report every skill twice.
            # This script is excluded because it necessarily contains the
            # literal marker it searches for.
            $rel -notlike '.specify/*' -and $rel -notlike '.git/*' -and
            $rel -notlike '.claude/skills/*' -and $rel -ne 'tools/verify-kit.ps1'
        } |
        Select-String -Pattern '\[FILL IN' -SimpleMatch
)
if ($placeholderHits.Count -gt 0) {
    $shown = $placeholderHits | Select-Object -First 20 | ForEach-Object {
        "$($_.Path.Substring($RepoRoot.Length + 1)):$($_.LineNumber)"
    }
    Add-Failure 'placeholders' "$($placeholderHits.Count) unfilled [FILL IN marker(s):`n    $($shown -join "`n    ")"
} else {
    Write-Host "  OK — none outside .specify/"
}

# --- 6. README image links ----------------------------------------------------
Write-Section "README image links"
$readmeImageProblems = 0
Get-ChildItem $RepoRoot -File -Filter 'README*.md' | ForEach-Object {
    $readme = $_
    [regex]::Matches((Get-Content $readme.FullName -Raw), '!\[[^\]]*\]\((docs/images/[^)\s]+)\)') | ForEach-Object {
        $imgRel = $_.Groups[1].Value
        if (-not (Test-Path (Join-Path $RepoRoot $imgRel))) {
            Add-Failure 'readme-images' "$($readme.Name) embeds '$imgRel' which does not exist"
            $readmeImageProblems++
        }
    }
}
if ($readmeImageProblems -eq 0) { Write-Host "  OK — every embedded docs/images/* resolves" }

# --- 7. LICENSE presence ------------------------------------------------------
Write-Section "LICENSE"
if (Test-Path (Join-Path $RepoRoot 'LICENSE')) {
    Write-Host "  OK"
} else {
    Add-Failure 'license' "README references a license but no LICENSE file exists at the repo root"
}

# --- Result -------------------------------------------------------------------
Write-Host ""
if ($warnings.Count -gt 0) {
    Write-Host "$($warnings.Count) warning(s):" -ForegroundColor Yellow
    $warnings | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    Write-Host ""
}
if ($failures.Count -gt 0) {
    Write-Host "FAILED — $($failures.Count) problem(s):" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}
Write-Host "All checks passed." -ForegroundColor Green
exit 0
